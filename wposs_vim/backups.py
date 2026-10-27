"""Respaldos con fecha y hora de la copia de trabajo y restauración validada."""
import logging
import os
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from .excel_store import ExcelLockedError, StoreError, excel_lock_present, validate_workbook_file

log = logging.getLogger("wposs.respaldos")
NAME_RE = re.compile(r"^(auto|manual|previo_restauracion)_\d{8}_\d{6}(_\d+)?\.xlsx$")


class BackupManager:
    def __init__(self, paths, config):
        self.paths = paths
        self.config = config

    def _target(self, kind):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.paths.respaldos / f"{kind}_{stamp}.xlsx"
        n = 1
        while target.exists():
            target = self.paths.respaldos / f"{kind}_{stamp}_{n}.xlsx"
            n += 1
        return target

    def create(self, kind="manual"):
        if not self.paths.trabajo.exists():
            raise StoreError("No existe la copia de trabajo para respaldar.")
        self.paths.respaldos.mkdir(parents=True, exist_ok=True)
        target = self._target(kind)
        shutil.copy2(self.paths.trabajo, target)
        log.info("Respaldo %s creado: %s", kind, target.name)
        if kind == "auto":
            self.prune()
        return target.name

    def maybe_auto(self):
        """Respaldo automático antes de escribir si el último es más antiguo que el intervalo."""
        minutes = int(self.config["respaldos"].get("intervalo_minutos", 60))
        autos = sorted(self.paths.respaldos.glob("auto_*.xlsx"), key=lambda p: p.stat().st_mtime)
        if autos and time.time() - autos[-1].stat().st_mtime < minutes * 60:
            return None
        return self.create("auto")

    def prune(self):
        keep = max(int(self.config["respaldos"].get("retener", 30)), 1)
        autos = sorted(self.paths.respaldos.glob("auto_*.xlsx"), key=lambda p: p.stat().st_mtime)
        for old in autos[:-keep]:
            try:
                old.unlink()
                log.info("Respaldo automático depurado por retención: %s", old.name)
            except OSError:
                pass

    def list(self):
        items = []
        for path in sorted(self.paths.respaldos.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not NAME_RE.match(path.name):
                continue
            st = path.stat()
            items.append({"nombre": path.name, "tipo": path.name.split("_")[0],
                          "tamano": st.st_size,
                          "fecha": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
        return items

    def path_of(self, name):
        if not NAME_RE.match(name or ""):
            raise StoreError("Nombre de respaldo no válido.")
        path = (self.paths.respaldos / name).resolve()
        if path.parent != self.paths.respaldos.resolve() or not path.exists():
            raise StoreError("El respaldo no existe.")
        return path

    def restore(self, name, store):
        """Valida el respaldo, guarda el estado actual y lo reemplaza."""
        source = self.path_of(name)
        problems = validate_workbook_file(source)
        if problems:
            raise StoreError("El respaldo no es válido: " + " ".join(problems))
        with store._lock:
            if excel_lock_present(self.paths.trabajo):
                raise ExcelLockedError("El libro está abierto en Excel. Ciérrelo antes de restaurar.")
            if store.pending():
                raise StoreError("Hay cambios pendientes de escribir. Aplíquelos o revíselos antes de restaurar.")
            previous = self.create("previo_restauracion")
            tmp = self.paths.trabajo.parent / f".tmp_{uuid.uuid4().hex}.xlsx"
            shutil.copy2(source, tmp)
            try:
                os.replace(tmp, self.paths.trabajo)
            except PermissionError:
                raise ExcelLockedError("El libro está bloqueado por otro programa.")
            finally:
                if tmp.exists():
                    tmp.unlink()
            store.invalidate()
            store.initialize()
            log.info("Respaldo restaurado: %s (estado anterior en %s)", name, previous)
            return previous
