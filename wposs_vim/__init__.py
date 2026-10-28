"""WPOSS Vending Integration Manager."""
import logging
from pathlib import Path

from flask import Flask

from .backups import BackupManager
from .config import Paths, load_config
from .evidence import EvidenceManager
from .excel_store import ExcelStore
from .operations import Operations
from .security import install, load_secret_key, setup_logging
from .services import Service

APP_NAME = "WPOSS Vending Integration Manager"
APP_VERSION = "1.0.0"


def create_app(base_dir=None, config_overrides=None, testing=False):
    base_dir = Path(base_dir or Path(__file__).resolve().parent.parent)
    config = load_config(base_dir, config_overrides)
    paths = Paths.from_config(base_dir, config)
    paths.ensure()
    logger = setup_logging(paths.logs)

    backups = BackupManager(paths, config)
    store = ExcelStore(paths, Operations(), before_write=backups.maybe_auto)
    store.initialize()

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=load_secret_key(paths.datos / ".secret_key"),
        # Límite por solicitud (varios archivos); el límite por archivo lo aplica EvidenceManager.
        MAX_CONTENT_LENGTH=int(config["evidencias"]["tamano_maximo_solicitud_mb"]) * 1024 * 1024,
        TESTING=testing,
        JSON_AS_ASCII=False,
    )
    evidence = EvidenceManager(paths.evidencias, config, paths.papelera)
    app.extensions["wposs"] = {
        "config": config, "paths": paths, "store": store, "service": Service(store, config, evidence),
        "evidence": evidence, "backups": backups, "base_dir": base_dir,
    }
    install(app, config["servidor"]["puerto"])

    from .routes import bp
    app.register_blueprint(bp)

    # Si quedaron cambios pendientes de una ejecución anterior, se intentan aplicar.
    if store.pending():
        try:
            store.retry_pending()
        except Exception as exc:  # el libro sigue bloqueado: se reintentará después
            logger.warning("No se pudieron aplicar los cambios pendientes al iniciar: %s", exc)
    logging.getLogger("wposs").info("Aplicación iniciada (%s)", paths.trabajo)
    return app
