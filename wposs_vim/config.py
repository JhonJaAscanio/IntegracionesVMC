"""Configuración local (config.json) y rutas de trabajo."""
import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG = {
    "servidor": {"host": "127.0.0.1", "puerto": 5000},
    "excel": {
        # Libro original de referencia. Nunca se modifica.
        "original": "WPOSS_Checklist_Pruebas_Vending_5320.xlsx",
        # Copia de trabajo controlada (almacenamiento principal).
        "trabajo": "data/trabajo/WPOSS_Vending_Datos.xlsx",
    },
    "carpetas": {
        "datos": "data",
        "evidencias": "data/evidencias",
        # Archivos eliminados de una visita (recuperables manualmente).
        "papelera": "data/papelera",
        "pendientes": "data/pendientes",
        "exportaciones": "data/exportaciones",
        "respaldos": "respaldos",
        "logs": "logs",
    },
    "respaldos": {
        # Respaldo automático antes de escribir si el último tiene más de N minutos.
        "intervalo_minutos": 60,
        # Cantidad de respaldos automáticos a conservar (los manuales no se podan).
        "retener": 30,
    },
    "evidencias": {
        "tamano_maximo_mb": 25,
        # Máximo total por envío del formulario (varios archivos a la vez).
        "tamano_maximo_solicitud_mb": 200,
        "extensiones": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "heic",
                        "pdf", "txt", "log", "csv", "json", "xml", "bin", "hex",
                        "zip", "7z", "doc", "docx", "xls", "xlsx", "mp4", "mov"],
    },
    "datos": {
        # Excluir de dashboard, totales y reportes los registros marcados como
        # "Fila de ejemplo" en el libro original.
        "excluir_ejemplos": True,
    },
    # Criterios de cierre. El libro original NO los define (ver hoja
    # Instrucciones, pregunta abierta: "¿Cuáles son los criterios de salida
    # para considerar una combinación apta para piloto?"). Estos valores son
    # una configuración explícita y conservadora, no un requisito técnico.
    "cierre": {
        "apto_requiere_cero_fallidas": True,
        "apto_requiere_cero_bloqueadas": True,
        "apto_requiere_cero_pendientes": True,
        "apto_requiere_cero_incidencias_abiertas": True,
        "apto_requiere_revision_fisica_sin_fallos": True,
        "condiciones_requiere_pendientes_documentados": True,
        # Componentes que deben tener al menos una prueba Aprobada para
        # declarar "Apto para piloto". Vacío = sin componentes críticos
        # definidos (pendiente de confirmar con el equipo WPOSS).
        "componentes_criticos": [],
    },
    "sesiones": {
        # Objetivo que se propone al elegir el tipo de prueba de la visita (editable en el formulario).
        "objetivos_por_tipo": {
            "Nueva Integración": (
                "Realizar la integración inicial del POS NEW5320 con la máquina vending y determinar si la "
                "combinación máquina–POS–versiones puede integrarse: verificar el estado físico y eléctrico y las "
                "conexiones, la comunicación MDB (dirección cashless, inicio de sesión de venta y respuestas del VMC), "
                "la autorización financiera de punta a punta y la dispensación correcta del producto, y concluir si "
                "la integración es apta para continuar a piloto."),
            "Reintegración": (
                "Volver a integrar el POS NEW5320 en una máquina vending ya trabajada, revisando las configuraciones "
                "vigentes de la máquina y del POS (parámetros y dirección MDB, precios y selecciones, firmware, "
                "versión Financiera y Agente Polaris) frente a la integración anterior, para identificar los cambios "
                "y confirmar que el ciclo completo de venta, pago y dispensación funciona con la nueva configuración."),
            "Validación de correcciones": (
                "Validar en sitio los ajustes y correcciones realizados por el comercio o el fabricante en la máquina "
                "vending después de la visita anterior: repetir los casos de prueba afectados, confirmar que las "
                "incidencias reportadas quedaron resueltas y comprobar que los cambios no introdujeron nuevas fallas "
                "en la comunicación MDB, el pago ni la dispensación."),
            "Integración de seguimiento": (
                "Dar seguimiento a una integración en curso o en piloto: revisar el comportamiento del POS y de la "
                "máquina vending en operación real, verificar la estabilidad de las transacciones y de la dispensación, "
                "cerrar los pendientes registrados en visitas anteriores y documentar el estado para definir el "
                "siguiente paso de la integración."),
        },
    },
    "pruebas": {
        # Prefijos para generar el ID de prueba según el componente.
        "prefijos": {
            "Máquina Vending": "MAQ",
            "POS NEW5320": "POS",
            "MDB": "MDB",
            "Financiera": "FIN",
            "Agente Polaris": "AGP",
            "Operación / Dispensación": "VEN",
            "Otro": "OTR",
        },
        # Si es True, una prueba no puede marcarse Aprobada sin evidencia adjunta.
        "exigir_evidencia_para_aprobar": False,
    },
}


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(base_dir, overrides=None):
    """Lee config.json del directorio base; lo crea con valores por defecto si falta."""
    base_dir = Path(base_dir)
    path = base_dir / "config.json"
    data = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(DEFAULT_CONFIG, fh, ensure_ascii=False, indent=2)
    config = _deep_merge(DEFAULT_CONFIG, data)
    if overrides:
        config = _deep_merge(config, overrides)
    return config


def save_config(base_dir, config):
    path = Path(base_dir) / "config.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


@dataclass
class Paths:
    base: Path
    original: Path
    trabajo: Path
    original_copia: Path
    datos: Path
    evidencias: Path
    papelera: Path
    pendientes: Path
    exportaciones: Path
    respaldos: Path
    logs: Path

    @classmethod
    def from_config(cls, base_dir, config):
        base = Path(base_dir).resolve()

        def p(value):
            path = Path(value)
            return (path if path.is_absolute() else base / path).resolve()

        carpetas = config["carpetas"]
        datos = p(carpetas["datos"])
        original = p(config["excel"]["original"])
        return cls(
            base=base,
            original=original,
            trabajo=p(config["excel"]["trabajo"]),
            original_copia=datos / "original" / original.name,
            datos=datos,
            evidencias=p(carpetas["evidencias"]),
            papelera=p(carpetas["papelera"]),
            pendientes=p(carpetas["pendientes"]),
            exportaciones=p(carpetas["exportaciones"]),
            respaldos=p(carpetas["respaldos"]),
            logs=p(carpetas["logs"]),
        )

    def ensure(self):
        for folder in (self.datos, self.trabajo.parent, self.original_copia.parent,
                       self.evidencias, self.papelera, self.pendientes, self.exportaciones,
                       self.respaldos, self.logs):
            folder.mkdir(parents=True, exist_ok=True)
