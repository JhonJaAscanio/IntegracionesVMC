"""Acceso solo local, protección CSRF, clave secreta local y redacción de logs."""
import hmac
import logging
import re
import secrets
from logging.handlers import RotatingFileHandler

from flask import abort, request, session

LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
_PAN = re.compile(r"(?<!\d)(\d[ -]?){12,18}\d(?!\d)")


def load_secret_key(path):
    """Clave de sesión generada en el equipo; nunca se incluye en el código."""
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    return key


def install(app, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost", f"[::1]:{port}"}

    @app.before_request
    def _local_only():
        if request.remote_addr not in LOOPBACK:
            abort(403)
        # Evita ataques de DNS rebinding: solo nombres locales en la cabecera Host.
        if not app.config.get("TESTING") and request.host not in allowed_hosts:
            abort(403)
        if request.method == "POST":
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
            expected = session.get("_csrf", "")
            if not expected or not hmac.compare_digest(sent, expected):
                abort(400, "Token de seguridad inválido. Recargue la página e inténtelo de nuevo.")

    @app.context_processor
    def _csrf():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["_csrf"]}

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; object-src 'none'; frame-ancestors 'self'")
        return resp


class RedactFilter(logging.Filter):
    """Enmascara secuencias con forma de número de tarjeta en los logs."""

    def filter(self, record):
        msg = record.getMessage()
        redacted = _PAN.sub(lambda m: "[REDACTADO]", msg)
        if redacted != msg:
            record.msg, record.args = redacted, ()
        return True


def setup_logging(logs_dir):
    logger = logging.getLogger("wposs")
    if any(isinstance(h, RotatingFileHandler) and getattr(h, "_wposs_dir", None) == str(logs_dir)
           for h in logger.handlers):
        return logger
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs_dir / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler._wposs_dir = str(logs_dir)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    handler.addFilter(RedactFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
