"""Operaciones de escritura serializables sobre el libro.

Cada operación recibe el libro abierto y un payload JSON. Las operaciones
comprueban sus precondiciones antes de modificar celdas, registran el
historial de cambios en App_Historial y nunca tocan filas ajenas.
"""
import re
from datetime import datetime

from . import schema as S
from .excel_store import (CIERRE_FORMULA_KEYS, ConflictError, StoreError,
                          catalog_column, cierre_formulas, norm_value, set_cell, sheet)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _history(wb, tipo, registro_id, sesion_id, accion, changes=None):
    hist = sheet(wb, S.SHEET_APP_HISTORIAL)
    now = _now()
    if not changes:
        hist.append({"fecha": now, "tipo_registro": tipo, "registro_id": registro_id,
                     "sesion_id": sesion_id, "accion": accion})
        return
    for campo, (old, new) in changes.items():
        hist.append({"fecha": now, "tipo_registro": tipo, "registro_id": registro_id,
                     "sesion_id": sesion_id, "campo": campo, "anterior": old,
                     "nuevo": new, "accion": accion})


def _diff(sh, rec, fields):
    labels = dict(sh.columns)
    changes = {}
    for key, value in fields.items():
        if key not in sh.col or key.startswith("_"):
            continue
        old = rec.get(key, "")
        new = "" if value is None else str(value)
        if old != new:
            changes[labels[key]] = (old, new)
    return changes


def _update_fields(sh, rec, fields):
    for key, value in fields.items():
        if key in sh.col and not key.startswith("_"):
            set_cell(sh.ws.cell(rec["_row"], sh.col[key]), value)


def _bump_counter(wb, record_id):
    m = re.match(r"^([A-Z]+)-(\d+)$", record_id or "")
    if not m:
        return
    prefix, number = m.group(1), int(m.group(2))
    cont = sheet(wb, S.SHEET_APP_CONTADORES)
    rec = cont.find(prefijo=prefix)
    if rec is None:
        cont.append({"prefijo": prefix, "ultimo": number})
    elif int(rec["ultimo"] or 0) < number:
        cont.ws.cell(rec["_row"], cont.col["ultimo"]).value = number


def _touch_session(wb, sesion_id, estado=None):
    meta = sheet(wb, S.SHEET_APP_SESIONES)
    rec = meta.find(sesion_id=sesion_id)
    if rec is None:
        meta.append({"sesion_id": sesion_id, "estado_registro": estado or S.ESTADO_REGISTRO_EN_CURSO,
                     "creado": _now(), "modificado": _now(), "origen": "Aplicación"})
        return
    meta.ws.cell(rec["_row"], meta.col["modificado"]).value = _now()
    if estado and rec.get("estado_registro") != estado:
        meta.ws.cell(rec["_row"], meta.col["estado_registro"]).value = estado
        _history(wb, "Sesión", sesion_id, sesion_id, "Cambio de estado de registro",
                 {"Estado de registro": (rec.get("estado_registro", ""), estado)})


def _require_session(wb, sesion_id):
    if sheet(wb, S.SHEET_ID).find(sesion_id=sesion_id) is None:
        raise ConflictError(f"La sesión {sesion_id} no existe.")


# --------------------------------------------------------------------------
# Sesiones
# --------------------------------------------------------------------------

def create_session(wb, p):
    ident = sheet(wb, S.SHEET_ID)
    sid = p["sesion"]["sesion_id"]
    if ident.find(sesion_id=sid) is not None:
        raise ConflictError(f"El Sesión ID {sid} ya existe; no se sobrescribe.")
    ident.append(p["sesion"])
    meta = sheet(wb, S.SHEET_APP_SESIONES)
    if meta.find(sesion_id=sid) is None:
        meta.append({"sesion_id": sid, "estado_registro": p["estado_registro"],
                     "creado": _now(), "modificado": _now(), "origen": "Aplicación"})
    _bump_counter(wb, sid)
    _history(wb, "Sesión", sid, sid, f"Creación ({p['estado_registro']})")


def update_session(wb, p):
    ident = sheet(wb, S.SHEET_ID)
    sid = p["sesion_id"]
    rec = ident.find(sesion_id=sid)
    if rec is None:
        raise ConflictError(f"La sesión {sid} no existe.")
    fields = {k: v for k, v in p["fields"].items() if k != "sesion_id"}
    changes = _diff(ident, rec, fields)
    _update_fields(ident, rec, fields)
    if changes:
        _history(wb, "Sesión", sid, sid, "Edición", changes)
    _touch_session(wb, sid, p.get("estado_registro"))


# --------------------------------------------------------------------------
# Revisión física y eléctrica
# --------------------------------------------------------------------------

def init_revision(wb, p):
    sid = p["sesion_id"]
    _require_session(wb, sid)
    rev = sheet(wb, S.SHEET_REVISION)
    existing = {r["item"] for r in rev.rows() if r["sesion_id"] == sid}
    added = []
    for item in p["items"]:
        if item and item not in existing:
            rev.append({"sesion_id": sid, "item": item, "resultado": S.ESTADO_PENDIENTE})
            existing.add(item)
            added.append(item)
    if added:
        _history(wb, "Revisión física", sid, sid, f"Ítems agregados: {'; '.join(added)}")
    _touch_session(wb, sid)


def update_revision(wb, p):
    sid = p["sesion_id"]
    rev = sheet(wb, S.SHEET_REVISION)
    rows = {r["item"]: r for r in rev.rows() if r["sesion_id"] == sid}
    for entry in p["items"]:
        rec = rows.get(entry["item"])
        if rec is None:
            raise ConflictError(f"El ítem '{entry['item']}' no existe en la sesión {sid}.")
        fields = {k: v for k, v in entry.items() if k in ("resultado", "observaciones")}
        changes = _diff(rev, rec, fields)
        if changes:
            _update_fields(rev, rec, fields)
            _history(wb, "Revisión física", entry["item"], sid, "Edición", changes)
    _touch_session(wb, sid)


# --------------------------------------------------------------------------
# Casos de prueba
# --------------------------------------------------------------------------

def create_test(wb, p):
    casos = sheet(wb, S.SHEET_CASOS)
    test = p["prueba"]
    _require_session(wb, test["sesion_id"])
    if casos.find(id=test["id"]) is not None:
        raise ConflictError(f"El ID de prueba {test['id']} ya existe.")
    casos.append(test)
    _bump_counter(wb, test["id"])
    _history(wb, "Prueba", test["id"], test["sesion_id"], f"Creación (estado {test.get('estado', '')})")
    _touch_session(wb, test["sesion_id"])


def update_test(wb, p):
    casos = sheet(wb, S.SHEET_CASOS)
    rec = casos.find(id=p["id"])
    if rec is None:
        raise ConflictError(f"La prueba {p['id']} no existe.")
    fields = {k: v for k, v in p["fields"].items() if k not in ("id", "sesion_id")}
    changes = _diff(casos, rec, fields)
    _update_fields(casos, rec, fields)
    if changes:
        _history(wb, "Prueba", p["id"], rec["sesion_id"], "Edición", changes)
    _touch_session(wb, rec["sesion_id"])


def _link_incident_to_test(wb, test_id, inc_id):
    casos = sheet(wb, S.SHEET_CASOS)
    rec = casos.find(id=test_id)
    if rec is None:
        raise ConflictError(f"La prueba {test_id} no existe.")
    current = [x.strip() for x in re.split(r"[;,]", rec.get("incidencia", "")) if x.strip()]
    if inc_id not in current:
        new = "; ".join(current + [inc_id])
        set_cell(casos.ws.cell(rec["_row"], casos.col["incidencia"]), new)
        _history(wb, "Prueba", test_id, rec["sesion_id"], "Incidencia asociada",
                 {"Incidencia asociada": (rec.get("incidencia", ""), new)})


# --------------------------------------------------------------------------
# Incidencias
# --------------------------------------------------------------------------

def create_incident(wb, p):
    incs = sheet(wb, S.SHEET_INCIDENCIAS)
    inc = p["incidencia"]
    _require_session(wb, inc["sesion_id"])
    if incs.find(id=inc["id"]) is not None:
        raise ConflictError(f"El ID de incidencia {inc['id']} ya existe.")
    if inc.get("prueba_id"):
        test = sheet(wb, S.SHEET_CASOS).find(id=inc["prueba_id"])
        if test is None:
            raise ConflictError(f"La prueba {inc['prueba_id']} no existe.")
        if test["sesion_id"] != inc["sesion_id"]:
            raise ConflictError("La prueba asociada pertenece a otra sesión.")
    incs.append(inc)
    _bump_counter(wb, inc["id"])
    _history(wb, "Incidencia", inc["id"], inc["sesion_id"], f"Creación (estado {inc.get('estado', '')})")
    if inc.get("prueba_id"):
        _link_incident_to_test(wb, inc["prueba_id"], inc["id"])
    _touch_session(wb, inc["sesion_id"])


def update_incident(wb, p):
    incs = sheet(wb, S.SHEET_INCIDENCIAS)
    rec = incs.find(id=p["id"])
    if rec is None:
        raise ConflictError(f"La incidencia {p['id']} no existe.")
    fields = {k: v for k, v in p["fields"].items() if k not in ("id", "sesion_id")}
    if fields.get("prueba_id") and fields["prueba_id"] != rec.get("prueba_id"):
        test = sheet(wb, S.SHEET_CASOS).find(id=fields["prueba_id"])
        if test is None or test["sesion_id"] != rec["sesion_id"]:
            raise ConflictError("La prueba asociada no existe en la misma sesión.")
    changes = _diff(incs, rec, fields)
    _update_fields(incs, rec, fields)
    if changes:
        _history(wb, "Incidencia", p["id"], rec["sesion_id"], p.get("accion") or "Edición", changes)
    if fields.get("prueba_id"):
        _link_incident_to_test(wb, fields["prueba_id"], p["id"])
    _touch_session(wb, rec["sesion_id"])


# --------------------------------------------------------------------------
# Cierre de sesión
# --------------------------------------------------------------------------

def save_cierre(wb, p):
    sid = p["sesion_id"]
    _require_session(wb, sid)
    cierre = sheet(wb, S.SHEET_CIERRE)
    fields = {k: v for k, v in p["fields"].items() if k in S.CIERRE_INPUT_KEYS}
    fields["sesion_id"] = sid
    rec = cierre.find(sesion_id=sid)
    if rec is None:
        # Primera fila libre (las filas preparadas ya traen las fórmulas).
        row = cierre.last_used_row() + 1
        cierre.write(row, fields, calc_keys=CIERRE_FORMULA_KEYS)
        _history(wb, "Cierre", sid, sid, "Creación del cierre",
                 {dict(cierre.columns)[k]: ("", str(v)) for k, v in fields.items() if v and k != "sesion_id"})
    else:
        row = rec["_row"]
        changes = _diff(cierre, rec, fields)
        _update_fields(cierre, rec, fields)
        if changes:
            _history(wb, "Cierre", sid, sid, "Edición del cierre", changes)
    # Restituye las fórmulas originales si la fila no las tiene.
    for key, formula in cierre_formulas(row).items():
        cell = cierre.ws.cell(row, cierre.col[key])
        if not (isinstance(cell.value, str) and cell.value.startswith("=")):
            cell.value = formula
    _touch_session(wb, sid, S.ESTADO_REGISTRO_CERRADA if fields.get("concepto") else None)


# --------------------------------------------------------------------------
# Catálogos, evidencias y registros de ejemplo
# --------------------------------------------------------------------------

def add_catalog_value(wb, p):
    key, value = p["catalog"], p["value"].strip()
    col = catalog_column(wb, key)
    if col is None:
        raise StoreError(f"El catálogo '{key}' no existe en la hoja Listas.")
    ws = wb[S.SHEET_LISTAS]
    last = 1
    for r in range(2, ws.max_row + 1):
        v = norm_value(ws.cell(r, col).value)
        if v:
            if v.casefold() == value.casefold():
                return  # ya existe: no se duplica
            last = r
    set_cell(ws.cell(last + 1, col), value)
    _history(wb, "Catálogo", S.CATALOG_LABELS[key], "", "Valor agregado", {"Valor": ("", value)})


_EVIDENCE_TARGET = {
    "Prueba": (S.SHEET_CASOS, "id"),
    "Incidencia": (S.SHEET_INCIDENCIAS, "id"),
    "Revisión física": (S.SHEET_REVISION, "item"),
}


def add_evidence(wb, p):
    meta = p["evidencia"]
    _require_session(wb, meta["sesion_id"])
    ev = sheet(wb, S.SHEET_APP_EVIDENCIAS)
    if ev.find(id=meta["id"]) is not None:
        raise ConflictError(f"La evidencia {meta['id']} ya existe.")
    if ev.find(ruta=meta["ruta"]) is not None:
        raise ConflictError("Ya existe una evidencia registrada con esa ruta.")
    target = _EVIDENCE_TARGET.get(meta["tipo_registro"])
    if target:
        sh = sheet(wb, target[0])
        criteria = {target[1]: meta["registro_id"]}
        if meta["tipo_registro"] == "Revisión física":
            criteria["sesion_id"] = meta["sesion_id"]
        rec = sh.find(**criteria)
        if rec is None:
            raise ConflictError(f"No existe el registro {meta['registro_id']} para asociar la evidencia.")
        current = rec.get("evidencia", "")
        new = f"{current}; {meta['ruta']}" if current else meta["ruta"]
        set_cell(sh.ws.cell(rec["_row"], sh.col["evidencia"]), new)
    ev.append(meta)
    _bump_counter(wb, meta["id"])
    _history(wb, "Evidencia", meta["id"], meta["sesion_id"],
             f"Archivo adjunto a {meta['tipo_registro']} {meta['registro_id']}",
             {"Ruta": ("", meta["ruta"])})
    _touch_session(wb, meta["sesion_id"])


def delete_example(wb, p):
    """Vacía una fila marcada como ejemplo (decisión explícita del usuario)."""
    tipo, rid = p["tipo"], p["id"]
    name = {"Prueba": S.SHEET_CASOS, "Incidencia": S.SHEET_INCIDENCIAS}[tipo]
    sh = sheet(wb, name)
    rec = sh.find(id=rid)
    if rec is None:
        raise ConflictError(f"{tipo} {rid} no existe.")
    text = " ".join(str(v) for k, v in rec.items() if k != "_row").casefold()
    if S.EXAMPLE_MARKER not in text:
        raise ConflictError(f"{tipo} {rid} no está marcado como fila de ejemplo; no se elimina.")
    snapshot = {dict(sh.columns)[k]: (v, "") for k, v in rec.items() if k in sh.col and v}
    sh.clear_row(rec["_row"])
    _history(wb, tipo, rid, rec.get("sesion_id", ""), "Fila de ejemplo eliminada", snapshot)


def set_session_state(wb, p):
    _require_session(wb, p["sesion_id"])
    _touch_session(wb, p["sesion_id"], p["estado_registro"])


class Operations:
    REGISTRY = {
        "create_session": create_session,
        "update_session": update_session,
        "init_revision": init_revision,
        "update_revision": update_revision,
        "create_test": create_test,
        "update_test": update_test,
        "create_incident": create_incident,
        "update_incident": update_incident,
        "save_cierre": save_cierre,
        "add_catalog_value": add_catalog_value,
        "add_evidence": add_evidence,
        "delete_example": delete_example,
        "set_session_state": set_session_state,
    }

    def apply(self, wb, name, payload):
        fn = self.REGISTRY.get(name)
        if fn is None:
            raise StoreError(f"Operación desconocida: {name}")
        fn(wb, payload)
