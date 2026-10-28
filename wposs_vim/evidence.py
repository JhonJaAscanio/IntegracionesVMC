"""Gestión de evidencias: carpeta por visita en data/evidencias/<Sesión ID>/<subcarpeta>/."""
import hashlib
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .validators import SESSION_ID_RE, ValidationError

TEXT_EXTENSIONS = {"txt", "log", "csv", "json", "xml", "hex"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "heic"}
WEB_IMAGE_EXTENSIONS = IMAGE_EXTENSIONS - {"heic"}
VIDEO_EXTENSIONS = {"mp4", "mov"}
LOG_EXTENSIONS = TEXT_EXTENSIONS | {"bin", "zip", "7z"}
RECORD_TYPES = ["Visita", "Revisión física", "Prueba", "Incidencia"]

CATEGORIA_INFORME = "Informe generado"
CATEGORIA_LOG_NEW5320 = "Log del POS NEW5320"
CATEGORIA_LOG_QIBIXX = "Log de Qibixx"
CATEGORIA_LOG = "Log de la visita"
# Categoría → (subcarpeta, prefijo del nombre de archivo, extensiones admitidas o None = todas).
CATEGORIES = {
    "Foto de la máquina": ("fotos", "maquina", IMAGE_EXTENSIONS),
    "Foto de etiqueta": ("fotos", "etiqueta", IMAGE_EXTENSIONS),
    "Foto de conexiones": ("fotos", "conexiones", IMAGE_EXTENSIONS),
    "Captura de pantalla": ("fotos", "captura", IMAGE_EXTENSIONS),
    "Video": ("videos", "", VIDEO_EXTENSIONS),
    CATEGORIA_LOG_NEW5320: ("logs/new5320", "", LOG_EXTENSIONS),
    CATEGORIA_LOG_QIBIXX: ("logs/qibixx", "", LOG_EXTENSIONS),
    CATEGORIA_LOG: ("logs", "", LOG_EXTENSIONS),
    "Documento": ("documentos", "", None),
    CATEGORIA_INFORME: ("informes", "", {"html"}),
    "Otro": ("otros", "", None),
}
UPLOAD_CATEGORIES = [c for c in CATEGORIES if c != CATEGORIA_INFORME]
FOLDERS = ["fotos", "logs", "videos", "documentos", "informes", "otros"]
FOLDER_LABELS = {"fotos": "Fotos", "logs": "Logs", "videos": "Videos", "documentos": "Documentos",
                 "informes": "Informes", "otros": "Otros"}
# Subcarpetas dentro de logs/ (ruta relativa a la carpeta de la visita → etiqueta).
LOG_SUBFOLDERS = {"logs/new5320": "NEW5320", "logs/qibixx": "Qibixx"}
SUBFOLDER_CATEGORY = {"logs/new5320": CATEGORIA_LOG_NEW5320, "logs/qibixx": CATEGORIA_LOG_QIBIXX}
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


def extension(name):
    return name.rpartition(".")[2].lower() if "." in name else ""


def infer_category(filename):
    """Categoría por defecto según la extensión (también para registros sin categoría)."""
    ext = extension(filename)
    if ext in IMAGE_EXTENSIONS:
        return "Foto de la máquina"
    if ext in VIDEO_EXTENSIONS:
        return "Video"
    if ext in LOG_EXTENSIONS:
        return "Log de la visita"
    if ext == "html":
        return CATEGORIA_INFORME
    return "Documento"


def subfolder_of(evidencia):
    """Subcarpeta completa de una evidencia registrada (p. ej. logs/new5320)."""
    categoria = evidencia.get("categoria") or infer_category(evidencia.get("archivo", ""))
    return CATEGORIES.get(categoria, CATEGORIES["Otro"])[0]


def folder_of(evidencia):
    """Subcarpeta de primer nivel de una evidencia registrada (fotos, logs, ...)."""
    return subfolder_of(evidencia).split("/")[0]


def category_for_path(rel_path):
    """Categoría sugerida para un archivo según la subcarpeta donde fue copiado."""
    parts = rel_path.split("/")
    for sub, categoria in SUBFOLDER_CATEGORY.items():
        if "/".join(parts[2:-1]) == sub:
            return categoria
    return infer_category(parts[-1])


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
    def __init__(self, base_dir, config, trash_dir=None):
        self.base = Path(base_dir).resolve()
        self.config = config
        self.trash = Path(trash_dir).resolve() if trash_dir else self.base.parent / "papelera"

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

    def ensure_session_dir(self, sesion_id):
        """Crea la carpeta de la visita con sus subcarpetas."""
        folder = self.session_dir(sesion_id)
        for sub in FOLDERS + list(LOG_SUBFOLDERS):
            (folder / sub).mkdir(parents=True, exist_ok=True)
        return folder

    def validate(self, filename, content, categoria=None):
        """Valida un archivo. Devuelve (nombre seguro, extensión, categoría)."""
        if not filename:
            raise ValidationError({"archivo": "Seleccione un archivo."})
        safe = safe_filename(filename)
        ext = extension(safe)
        categoria = categoria or infer_category(safe)
        if categoria not in UPLOAD_CATEGORIES:
            raise ValidationError({"archivo": "Categoría de evidencia no válida."})
        if ext not in self.extensions:
            raise ValidationError({"archivo": f"{filename}: extensión no permitida (.{ext or '?'}). "
                                              f"Permitidas: {', '.join(sorted(self.extensions))}."})
        allowed = CATEGORIES[categoria][2]
        if allowed is not None and ext not in allowed:
            raise ValidationError({"archivo": f"{filename}: no corresponde a la categoría “{categoria}” "
                                              f"(se esperan: {', '.join(sorted(allowed))})."})
        if len(content) == 0:
            raise ValidationError({"archivo": f"{filename}: el archivo está vacío."})
        if len(content) > self.max_bytes:
            raise ValidationError({"archivo": f"{filename}: supera el máximo de "
                                              f"{self.config['evidencias']['tamano_maximo_mb']} MB."})
        return safe, ext, categoria

    def store(self, sesion_id, registro_id, filename, content, categoria=None):
        """Guarda el archivo sin sobrescribir. Devuelve metadatos (sin ID)."""
        safe, ext, categoria = self.validate(filename, content, categoria)
        return self._write(sesion_id, registro_id, safe, ext, categoria, content)

    def store_generated(self, sesion_id, filename, content):
        """Guarda un informe generado por la aplicación en la carpeta informes/."""
        safe = safe_filename(filename)
        return self._write(sesion_id, sesion_id, safe, extension(safe), CATEGORIA_INFORME, content)

    def _write(self, sesion_id, registro_id, safe, ext, categoria, content):
        sub, prefix, _ = CATEGORIES[categoria]
        folder = self.ensure_session_dir(sesion_id) / sub
        parts = []
        if registro_id and registro_id != sesion_id:
            parts.append(safe_filename(registro_id))
        if prefix:
            parts.append(prefix)
        lead = "_".join(parts) + "_" if parts else ""
        stem, _, ext_part = safe.rpartition(".")
        if not stem:
            stem, ext_part = safe, ""
        suffix = f".{ext_part}" if ext_part else ""
        candidate = folder / f"{lead}{stem}{suffix}"
        n = 1
        while candidate.exists():
            candidate = folder / f"{lead}{stem}-{n}{suffix}"
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
        return {
            "archivo": candidate.name, "ruta": candidate.relative_to(self.base.parent).as_posix(),
            "tamano": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            "tipo_archivo": ext, "advertencia": warning, "categoria": categoria,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def remove_file(self, rel_path):
        """Elimina un archivo recién guardado cuando no pudo registrarse."""
        path = self.resolve(rel_path)
        if path and path.exists():
            path.unlink()

    def move_to_trash(self, sesion_id, rel_path):
        """Mueve un archivo de la visita a la papelera. Devuelve la ruta en la papelera o None."""
        path = self.resolve(rel_path)
        folder = self.session_dir(sesion_id)
        if path is None or folder not in path.parents:
            raise ValidationError({"archivo": "El archivo no pertenece a la carpeta de la visita."})
        if not path.is_file():
            return None
        target_dir = self.trash / sesion_id
        target_dir.mkdir(parents=True, exist_ok=True)
        flat = path.relative_to(folder).as_posix().replace("/", "__")
        target = target_dir / f"{datetime.now():%Y%m%d_%H%M%S}__{flat}"
        n = 1
        while target.exists():
            target = target_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{n}__{flat}"
            n += 1
        os.replace(path, target)
        return target

    def restore_from_trash(self, trash_path, rel_path):
        """Devuelve a su lugar un archivo movido a la papelera (si la eliminación no se registró)."""
        path = self.resolve(rel_path)
        if path is not None and trash_path and Path(trash_path).exists() and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(trash_path, path)

    def resolve(self, rel_path):
        """Resuelve una ruta relativa registrada, restringida a la carpeta de evidencias."""
        path = (self.base.parent / rel_path).resolve()
        try:
            path.relative_to(self.base)
        except ValueError:
            return None
        return path

    def unregistered(self, sesion_id, registered_paths):
        """Archivos presentes en la carpeta de la visita que no están registrados en el libro."""
        folder = self.session_dir(sesion_id)
        if not folder.exists():
            return []
        found = []
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not path.name.startswith(("~$", ".")):
                rel = path.relative_to(self.base.parent).as_posix()
                if rel not in registered_paths:
                    found.append({"archivo": path.name, "ruta": rel, "tamano": path.stat().st_size,
                                  "carpeta": path.parent.relative_to(folder).as_posix()
                                  if path.parent != folder else ""})
        return found

    def register_existing(self, sesion_id, rel_path, categoria=None):
        """Metadatos de un archivo copiado manualmente a la carpeta de la visita."""
        path = self.resolve(rel_path)
        folder = self.session_dir(sesion_id)
        if path is None or not path.is_file() or folder not in path.parents:
            raise ValidationError({"archivo": "El archivo no pertenece a la carpeta de la visita."})
        content = path.read_bytes()
        safe = path.name
        ext = extension(safe)
        categoria = categoria or category_for_path(rel_path)
        if categoria not in UPLOAD_CATEGORIES:
            raise ValidationError({"archivo": "Categoría de evidencia no válida."})
        if ext not in self.extensions:
            raise ValidationError({"archivo": f"{safe}: extensión no permitida (.{ext or '?'})."})
        if len(content) > self.max_bytes:
            raise ValidationError({"archivo": f"{safe}: supera el tamaño máximo permitido."})
        warning = ""
        if ext in TEXT_EXTENSIONS and scan_sensitive(content):
            warning = "Se detectaron secuencias con formato de número de tarjeta. Revise y redacte el archivo."
        return {
            "archivo": safe, "ruta": rel_path, "tamano": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "tipo_archivo": ext, "advertencia": warning,
            "categoria": categoria, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def read_text(self, rel_path, limit=512 * 1024):
        """Contenido de un archivo de texto para visualizarlo (truncado al límite)."""
        path = self.resolve(rel_path)
        if path is None or not path.is_file():
            return None, False
        with open(path, "rb") as fh:
            data = fh.read(limit + 1)
        return data[:limit].decode("utf-8", errors="replace"), len(data) > limit
