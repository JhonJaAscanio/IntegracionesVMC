"""Validación de datos de entrada antes de escribir en el libro."""
import re
from datetime import datetime

from . import schema as S

MAX_TEXT = 4000
SESSION_ID_RE = re.compile(r"^SES-\d{3,6}$")
RECORD_ID_RE = re.compile(r"^[A-Z]{2,6}-\d{3,6}$")


class ValidationError(Exception):
    """Errores por campo: {campo: mensaje}."""

    def __init__(self, errors, message="Revise los campos marcados."):
        super().__init__(message)
        self.errors = errors
        self.message = message


def clean(form, keys):
    """Toma del formulario solo las claves permitidas, como texto sin espacios extremos."""
    data = {}
    for key in keys:
        value = form.get(key, "")
        if value is None:
            value = ""
        value = str(value).replace("\r\n", "\n").strip()
        data[key] = value
    return data


def _check_len(data, errors):
    for key, value in data.items():
        if len(value) > MAX_TEXT:
            errors[key] = f"Máximo {MAX_TEXT} caracteres."


def _check_date(data, key, errors):
    value = data.get(key, "")
    if value and value not in ("N/A", S.PENDIENTE_CONFIRMAR):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            errors[key] = "Use el formato AAAA-MM-DD."


def _check_time(data, key, errors):
    value = data.get(key, "")
    if value:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            errors[key] = "Use el formato HH:MM."


def _check_catalog(data, key, values, errors, label=None):
    value = data.get(key, "")
    if value and value not in values:
        errors[key] = f"Seleccione un valor válido{' de ' + label if label else ''}."


def _required(data, keys, errors):
    for key in keys:
        if not data.get(key):
            errors.setdefault(key, "Campo obligatorio.")


SESSION_FIELDS = [k for k, _ in S.ID_COLUMNS if k != "sesion_id"]
# Campos mínimos para pasar de borrador a sesión en curso. El libro no marca
# obligatorios; se exige la identificación básica del equipo y de la visita.
SESSION_REQUIRED = ["fecha", "responsable", "cliente", "fabricante", "modelo_maquina",
                    "modelo_pos", "objetivo", "tipo_prueba", "firmware"]


def validate_session(data, catalogs, draft, ciudades=None, current=None):
    """Valida la identificación de la sesión.

    `ciudades` = {país: [ciudades]}. Un valor de catálogo que ya tenía el registro
    (`current`) se acepta aunque ya no esté en la lista, para no forzar cambios en
    visitas anteriores.
    """
    errors = {}
    current = current or {}
    _check_len(data, errors)
    _check_date(data, "fecha", errors)
    _check_date(data, "fecha_instalacion", errors)
    _check_time(data, "hora", errors)

    def catalog(key, values):
        if data.get(key) and data[key] != current.get(key):
            _check_catalog(data, key, values, errors)

    catalog("tipo_prueba", catalogs["tipo_prueba"])
    catalog("pais", catalogs["pais"])
    catalog("cliente", catalogs.get("cliente", []))
    catalog("firmware", catalogs.get("firmware", []) + [S.PENDIENTE_CONFIRMAR])
    catalog("nivel_maquina", catalogs.get("nivel_maquina", []) + [S.PENDIENTE_CONFIRMAR])
    catalog("mdb_resultado", catalogs.get("resultado_prueba", []))
    catalog("dex_resultado", catalogs.get("resultado_prueba", []))
    catalog("dex_archivo", S.DEX_ARCHIVO_OPCIONES)
    # Una prueba fallida debe documentar qué se observó o qué error ocurrió.
    for resultado, observacion in (("mdb_resultado", "mdb_observacion"), ("dex_resultado", "dex_observacion")):
        if data.get(resultado) == S.RESULTADO_FALLIDA and not data.get(observacion):
            errors[observacion] = "Describa el error observado en la prueba fallida."
    if ciudades is not None and data.get("ciudad") and (
            data["ciudad"] != current.get("ciudad") or data.get("pais") != current.get("pais")):
        if not data.get("pais"):
            errors["ciudad"] = "Seleccione primero el país."
        elif data["ciudad"] not in ciudades.get(data["pais"], []):
            errors["ciudad"] = f"La ciudad no corresponde a {data['pais']}."
    if draft:
        if not any(data.get(k) for k in SESSION_FIELDS):
            errors["cliente"] = "Registre al menos un dato para guardar el borrador."
    else:
        _required(data, SESSION_REQUIRED, errors)
    if errors:
        raise ValidationError(errors)
    return data


TEST_FIELDS = [k for k, _ in S.CASOS_COLUMNS if k not in ("id", "evidencia", "incidencia")]


def validate_test(data, catalogs, config, has_evidence=False):
    errors = {}
    _check_len(data, errors)
    _required(data, ["sesion_id", "componente", "tipo_verificacion", "objetivo", "estado"], errors)
    _check_catalog(data, "componente", catalogs["componente"], errors)
    _check_catalog(data, "tipo_verificacion", catalogs["tipo_verificacion"], errors)
    _check_catalog(data, "estado", catalogs["estados"], errors)
    estado = data.get("estado")
    # Regla del libro: registrar el resultado esperado antes de ejecutar.
    if estado and estado != S.ESTADO_PENDIENTE and not data.get("resultado_esperado"):
        errors["resultado_esperado"] = "Registre el resultado esperado antes de cambiar el estado."
    # Regla del libro: no marcar Aprobado sin ejecución y evidencia suficiente.
    if estado in (S.ESTADO_APROBADO, S.ESTADO_FALLIDO):
        obtenido = data.get("resultado_obtenido", "")
        if not obtenido or obtenido == S.PENDIENTE_CONFIRMAR:
            errors["resultado_obtenido"] = f"Para marcar '{estado}' registre el resultado obtenido."
    if (estado == S.ESTADO_APROBADO and config["pruebas"].get("exigir_evidencia_para_aprobar")
            and not has_evidence):
        errors["estado"] = "La configuración exige evidencia adjunta para marcar Aprobado."
    if errors:
        raise ValidationError(errors)
    return data


INCIDENT_FIELDS = [k for k, _ in S.INCIDENCIAS_COLUMNS if k not in ("id", "evidencia")]


def validate_incident(data, catalogs):
    errors = {}
    _check_len(data, errors)
    _required(data, ["sesion_id", "fecha", "descripcion", "severidad", "estado"], errors)
    _check_date(data, "fecha", errors)
    _check_catalog(data, "severidad", catalogs["severidad"], errors)
    _check_catalog(data, "estado", catalogs["estado_incidencia"], errors)
    if data.get("prueba_id") and not RECORD_ID_RE.match(data["prueba_id"]):
        errors["prueba_id"] = "ID de prueba no válido."
    if errors:
        raise ValidationError(errors)
    return data


def validate_session_id(value):
    if not SESSION_ID_RE.match(value or ""):
        raise ValidationError({"sesion_id": "Sesión ID no válido."}, "Sesión ID no válido.")
    return value
