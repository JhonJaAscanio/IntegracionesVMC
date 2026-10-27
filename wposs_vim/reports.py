"""Exportación de registros a un libro nuevo (no modifica el libro principal)."""
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import schema as S

HEADER_FILL = PatternFill(fill_type="solid", fgColor="FF09919D")
HEADER_FONT = Font(bold=True, color="FFFFFFFF")


def _sheet(wb, title, columns, rows):
    ws = wb.create_sheet(title)
    for i, (_, header) in enumerate(columns, start=1):
        cell = ws.cell(1, i, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = 18
    for r, rec in enumerate(rows, start=2):
        for i, (key, _) in enumerate(columns, start=1):
            value = rec.get(key, "")
            cell = ws.cell(r, i)
            cell.value = value if value != "" else None
            if isinstance(value, str):
                cell.data_type = "s"
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"
    return ws


def export_workbook(service, sessions, folder):
    """Genera un .xlsx con las sesiones filtradas y sus registros relacionados."""
    data = service.data()
    sids = {s["sesion_id"] for s in sessions}
    wb = Workbook()
    wb.remove(wb.active)
    session_cols = S.ID_COLUMNS + [("estado_registro", "Estado de registro"),
                                   ("estado_integracion", "Estado de la integración")]
    _sheet(wb, "Sesiones", session_cols, sessions)
    _sheet(wb, "Revisión física", S.REVISION_COLUMNS, [r for r in data.revisiones if r["sesion_id"] in sids])
    _sheet(wb, "Casos de prueba", S.CASOS_COLUMNS, [t for t in data.pruebas if t["sesion_id"] in sids])
    _sheet(wb, "Incidencias", S.INCIDENCIAS_COLUMNS, [i for i in data.incidencias if i["sesion_id"] in sids])
    totals_cols = [("sesion_id", "Sesión ID"), ("planificadas", "Total planificadas"),
                   ("ejecutadas", "Total ejecutadas"), ("aprobadas", "Aprobadas"),
                   ("fallidas", "Fallidas"), ("bloqueadas", "Bloqueadas"),
                   ("pendientes", "Pendientes"), ("incidencias_abiertas", "Incidencias abiertas"),
                   ("concepto", "Concepto final")]
    totals = []
    for s in sessions:
        t = service.totals(s["sesion_id"], data)
        totals.append({**t, "sesion_id": s["sesion_id"], "concepto": s.get("concepto", "")})
    _sheet(wb, "Totales de cierre", totals_cols, totals)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"Exportacion_WPOSS_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    path = folder / name
    n = 1
    while path.exists():
        path = folder / f"Exportacion_WPOSS_{datetime.now():%Y%m%d_%H%M%S}_{n}.xlsx"
        n += 1
    wb.save(path)
    return path
