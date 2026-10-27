"""Gestión de evidencias: archivos en data/evidencias/<Sesión ID>/."""
import hashlib
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .validators import SESSION_ID_RE, ValidationError

TEXT_EXTENSIONS = {"txt", "log", "csv", "json", "xml", "hex"}
RECORD_TYPES = ["Visita", "Revisión física", "Prueba", "Incidencia"]
_PAN_CANDIDATE = re.compile(rb"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def safe_filename(name):
    """Nombre de archivo seguro: sin rutas, acentos ni caracteres especiales."""
    name = os.path.basename(str(name).replace("\\", "/"))
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = stem[:80] or "archivo"
    return f"{stem}.{ext.lower()}" if ext else stem


def _luhn(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def scan_sensitive(content):
    """Busca secuencias con forma de número de tarjeta (Luhn). No modifica el archivo."""
    hits = 0
    for m in _PAN_CANDIDATE.finditer(content):
        digits = re.sub(rb"\D", b"", m.group(0)).decode()
        if 13 <= len(digits) <= 19 and _luhn(digits) and len(set(digits)) > 1:
            hits += 1
    return hits


class EvidenceManager:
    def __init__(self, base_dir, config):
        self.base = Path(base_dir).resolve()
        self.config = config

    @property
    def max_bytes(self):
        return int(self.config["evidencias"]["tamano_maximo_mb"]) * 1024 * 1024

    @property
    def extensions(self):
        return {e.lower().lstrip(".") for e in self.config["evidencias"]["extensiones"]}

    def session_dir(self, sesion_id):
        if not SESSION_ID_RE.match(sesion_id or ""):
            raise ValidationError({"archivo": "Sesión ID no válido."}, "Sesión ID no válido.")
        path = (self.base / sesion_id).resolve()
        if path.parent != self.base:
            raise ValidationError({"archivo": "Ruta no permitida."}, "Ruta no permitida.")
        return path

    def validate(self, filename, content):
        if not filename:
            raise ValidationError({"archivo": "Seleccione un archivo."})
        safe = safe_filename(filename)
        ext = safe.rpartition(".")[2].lower() if "." in safe else ""
        if ext not in self.extensions:
            raise ValidationError({"archivo": f"Extensión no permitida (.{ext or '?'}). "
                                              f"Permitidas: {', '.join(sorted(self.extensions))}."})
        if len(content) == 0:
            raise ValidationError({"archivo": "El archivo está vacío."})
        if len(content) > self.max_bytes:
            raise ValidationError({"archivo": f"El archivo supera el máximo de "
                                              f"{self.config['evidencias']['tamano_maximo_mb']} MB."})
        return safe, ext

    def store(self, sesion_id, registro_id, filename, content):
        """Guarda el archivo sin sobrescribir. Devuelve metadatos (sin ID)."""
        safe, ext = self.validate(filename, content)
        folder = self.session_dir(sesion_id)
        folder.mkdir(parents=True, exist_ok=True)
        prefix = safe_filename(registro_id) + "_" if registro_id and registro_id != sesion_id else ""
        stem, _, ext_part = safe.rpartition(".")
        candidate = folder / f"{prefix}{safe}"
        n = 1
        while candidate.exists():
            candidate = folder / f"{prefix}{stem}-{n}.{ext_part}"
            n += 1
        # Creación exclusiva: nunca reemplaza un archivo existente.
        with open(candidate, "xb") as fh:
            fh.write(content)
        warning = ""
        if ext in TEXT_EXTENSIONS:
            hits = scan_sensitive(content)
            if hits:
                warning = (f"Se detectaron {hits} secuencia(s) con formato de número de tarjeta. "
                           "Revise y redacte los datos sensibles del archivo.")
        rel = candidate.relative_to(self.base.parent).as_posix()
        return {
            "archivo": candidate.name, "ruta": rel, "tamano": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "tipo_archivo": ext,
            "advertencia": warning, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def remove_file(self, rel_path):
        """Elimina un archivo recién guardado cuando no pudo registrarse."""
        path = self.resolve(rel_path)
        if path and path.exists():
            path.unlink()

    def resolve(self, rel_path):
        """Resuelve una ruta relativa registrada, restringida a la carpeta de evidencias."""
        path = (self.base.parent / rel_path).resolve()
        try:
            path.relative_to(self.base)
        except ValueError:
            return None
        return path
