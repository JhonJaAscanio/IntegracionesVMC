"""Rutas web."""
import json
import logging
import math
import os
from datetime import datetime

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, send_file, url_for)

from . import APP_NAME, APP_VERSION
from . import schema as S
from .config import save_config
from .evidence import (CATEGORIA_INFORME, CATEGORIA_LOG, FOLDER_LABELS, LOG_SUBFOLDERS, RECORD_TYPES,
                       SUBFOLDER_CATEGORY, TEXT_EXTENSIONS, UPLOAD_CATEGORIES, WEB_IMAGE_EXTENSIONS,
                       category_for_path, subfolder_of)
from .excel_store import ConflictError, ExcelLockedError, PendingWriteError, StoreError
from .reports import build_visit_zip, export_workbook, generate_visit_report, report_context
from .services import INTEGRATION_CATEGORIES
from .validators import SESSION_ID_RE, ValidationError

bp = Blueprint("main", __name__)
log = logging.getLogger("wposs.web")
PAGE_SIZE = 15


def ext():
    return current_app.extensions["wposs"]


def svc():
    return ext()["service"]


@bp.app_context_processor
def _globals():
    store = ext()["store"]
    return {
        "APP_NAME": APP_NAME, "APP_VERSION": APP_VERSION, "S": S,
        "pending_count": len(list(store.paths.pendientes.glob("*.json"))),
        "CATEGORIES": INTEGRATION_CATEGORIES,
    }


@bp.app_template_filter("estado_clase")
def estado_clase(value):
    v = (value or "").strip()
    if v in (S.ESTADO_APROBADO, S.CONCEPTO_APTO, S.INCIDENCIA_CERRADA, S.ESTADO_REGISTRO_CERRADA, "Exitosa"):
        return "ok"
    if v in (S.ESTADO_FALLIDO, S.CONCEPTO_NO_APTO, "Crítica", S.RESULTADO_FALLIDA):
        return "bad"
    if v in (S.ESTADO_BLOQUEADO, "Alta"):
        return "block"
    if v in (S.ESTADO_PENDIENTE, S.CONCEPTO_CONDICIONES, S.INCIDENCIA_ABIERTA, "En progreso",
             "Pendiente de reprueba", "En observación", S.ESTADO_REGISTRO_BORRADOR, "Media", "No realizada"):
        return "warn"
    return "neutral"


@bp.app_template_filter("tamano")
def tamano(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _write_errors(exc, pending_redirect=None):
    """Traduce errores de escritura a mensajes. Devuelve un redirect si aplica."""
    if isinstance(exc, PendingWriteError):
        flash(f"El cambio NO se guardó en el libro: {exc.reason} Quedó en cola "
              f"({exc.pending_count} cambio(s) pendiente(s)) y se aplicará al reintentar.", "warn")
        return redirect(pending_redirect or url_for("main.dashboard"))
    if isinstance(exc, ExcelLockedError):
        flash(str(exc), "error")
    elif isinstance(exc, ConflictError):
        flash(str(exc), "error")
    elif isinstance(exc, StoreError):
        log.error("Error de almacenamiento: %s", exc)
        flash(f"No se pudo guardar: {exc}", "error")
    return None


def _session_or_404(sid):
    if not SESSION_ID_RE.match(sid or ""):
        abort(404)
    s = svc().get_session(sid)
    if s is None:
        abort(404)
    return s


def _paginate(items, page):
    pages = max(1, math.ceil(len(items) / PAGE_SIZE))
    page = min(max(page, 1), pages)
    return items[(page - 1) * PAGE_SIZE: page * PAGE_SIZE], page, pages


def _args():
    return {k: v.strip() for k, v in request.args.items() if v and v.strip()}


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@bp.route("/")
def dashboard():
    f = _args()
    service = svc()
    stats = service.dashboard(f)
    options = service.filter_options(service.sessions())
    return render_template("dashboard.html", stats=stats, f=f, options=options, active="dashboard")


# --------------------------------------------------------------------------
# Visitas
# --------------------------------------------------------------------------

SORT_KEYS = {"id": "sesion_id", "fecha": "fecha", "cliente": "cliente", "maquina": "fabricante",
             "firmware": "firmware", "estado": "estado_integracion", "responsable": "responsable"}


@bp.route("/visitas")
def visitas():
    f = _args()
    service = svc()
    all_sessions = service.sessions()
    rows = service.filter_sessions(all_sessions, f)
    sort = f.get("orden", "fecha")
    desc = f.get("dir", "desc") == "desc"
    key = SORT_KEYS.get(sort, "fecha")
    rows.sort(key=lambda s: ((s.get(key) or "").casefold(), s["sesion_id"]), reverse=desc)
    page_rows, page, pages = _paginate(rows, int(request.args.get("pagina", 1) or 1))
    return render_template("visitas.html", rows=page_rows, total=len(rows), page=page, pages=pages,
                           f=f, sort=sort, desc=desc, options=service.filter_options(all_sessions),
                           active="visitas")


def _session_form_context(values=None, errors=None, sid=None):
    data = svc().data()
    return {"v": values or {}, "errors": errors or {}, "cat": data.catalogos, "sid": sid,
            "upload_fields": VISIT_UPLOAD_FIELDS, "ciudades": data.ciudades,
            "clientes_pais_json": json.dumps(data.clientes_pais, ensure_ascii=False),
            "ciudades_json": json.dumps(data.ciudades, ensure_ascii=False),
            "objetivos_json": json.dumps(svc().objective_templates(), ensure_ascii=False)}


LOG_ACCEPT = ".log,.txt,.csv,.json,.xml,.bin,.hex,.zip,.7z"

# Campos de archivos del paso "Evidencias" de la nueva visita: (campo, categoría, etiqueta, accept).
VISIT_UPLOAD_FIELDS = [
    ("fotos_maquina", "Foto de la máquina", "Fotos de la máquina", "image/*"),
    ("fotos_etiqueta", "Foto de etiqueta", "Fotos de etiquetas (placa, serial, POS)", "image/*"),
    ("fotos_conexiones", "Foto de conexiones", "Fotos de conexiones y cableado", "image/*"),
    ("capturas", "Captura de pantalla", "Capturas de pantalla", "image/*"),
    ("logs_new5320", "Log del POS NEW5320", "Logs del POS NEW5320", LOG_ACCEPT),
    ("logs_qibixx", "Log de Qibixx", "Logs de Qibixx", LOG_ACCEPT),
    ("archivos_dex", "Archivo DEX", "Archivos DEX (auditoría de la máquina)", LOG_ACCEPT + ",.dex"),
    ("logs", "Log de la visita", "Otros logs de la visita (sniffer, diagnóstico)", LOG_ACCEPT),
    ("documentos", "Documento", "Documentos", ""),
]


def _visit_files():
    descripcion = request.form.get("descripcion_evidencias", "").strip()
    files = []
    for field, categoria, _, _ in VISIT_UPLOAD_FIELDS:
        for fs in request.files.getlist(field):
            if fs and fs.filename:
                files.append((categoria, fs.filename, fs.read(), descripcion))
    return files


@bp.route("/visitas/nueva", methods=["GET", "POST"])
def visita_nueva():
    if request.method == "POST":
        draft = request.form.get("accion") == "borrador"
        try:
            files = _visit_files()
            sid = svc().create_session(request.form, draft=draft, files=files)
            extra = f" con {len(files)} archivo(s) en su carpeta" if files else ""
            flash(f"Sesión {sid} {'guardada como borrador' if draft else 'registrada'}{extra}.", "ok")
            return redirect(url_for("main.visita", sid=sid))
        except ValidationError as exc:
            flash(exc.message, "error")
            return render_template("visita_form.html", **_session_form_context(request.form, exc.errors),
                                   active="nueva"), 422
        except StoreError as exc:
            resp = _write_errors(exc, url_for("main.visitas"))
            if resp:
                return resp
            return render_template("visita_form.html", **_session_form_context(request.form),
                                   active="nueva"), 409
    defaults = {"fecha": datetime.now().strftime("%Y-%m-%d"), "hora": datetime.now().strftime("%H:%M"),
                "modelo_pos": "NEW5320"}
    return render_template("visita_form.html", **_session_form_context(defaults), active="nueva")


@bp.route("/visitas/<sid>/editar", methods=["GET", "POST"])
def visita_editar(sid):
    session = _session_or_404(sid)
    if request.method == "POST":
        draft = request.form.get("accion") == "borrador"
        try:
            svc().update_session(sid, request.form, draft=draft)
            flash(f"Sesión {sid} actualizada.", "ok")
            return redirect(url_for("main.visita", sid=sid))
        except ValidationError as exc:
            flash(exc.message, "error")
            return render_template("visita_form.html", **_session_form_context(request.form, exc.errors, sid),
                                   session=session, active="visitas"), 422
        except StoreError as exc:
            resp = _write_errors(exc, url_for("main.visita", sid=sid))
            if resp:
                return resp
            return render_template("visita_form.html", **_session_form_context(request.form, sid=sid),
                                   session=session, active="visitas"), 409
    return render_template("visita_form.html", **_session_form_context(session, sid=sid),
                           session=session, active="visitas")


@bp.route("/visitas/<sid>")
def visita(sid):
    _session_or_404(sid)
    service = svc()
    bundle = service.session_bundle(sid)
    tab = request.args.get("tab", "resumen")
    data = service.data()
    return render_template("visita_detalle.html", b=bundle, tab=tab, cat=data.catalogos,
                           totals=service.totals(sid, data), ev=service.evaluate_closure(sid, data),
                           record_types=RECORD_TYPES, upload_categories=UPLOAD_CATEGORIES,
                           legacy_fields=service.legacy_fields(bundle["sesion"]), active="visitas")


# --------------------------------------------------------------------------
# Revisión física y eléctrica
# --------------------------------------------------------------------------

@bp.route("/visitas/<sid>/revision/iniciar", methods=["POST"])
def revision_iniciar(sid):
    _session_or_404(sid)
    try:
        svc().init_revision(sid, request.form.get("item") or None)
        flash("Ítems de revisión agregados." if request.form.get("item") else
              "Lista de revisión física creada con los ítems del checklist.", "ok")
    except ValidationError as exc:
        flash(" ".join(exc.errors.values()) or exc.message, "error")
    except StoreError as exc:
        resp = _write_errors(exc, url_for("main.visita", sid=sid, tab="revision"))
        if resp:
            return resp
    return redirect(url_for("main.visita", sid=sid, tab="revision"))


@bp.route("/visitas/<sid>/revision", methods=["POST"])
def revision_guardar(sid):
    _session_or_404(sid)
    try:
        svc().update_revision(sid, request.form)
        flash("Revisión física guardada.", "ok")
    except ValidationError as exc:
        flash("Revise los resultados: " + "; ".join(exc.errors.values()), "error")
    except StoreError as exc:
        resp = _write_errors(exc, url_for("main.visita", sid=sid, tab="revision"))
        if resp:
            return resp
    return redirect(url_for("main.visita", sid=sid, tab="revision"))


@bp.route("/revision")
def revision_lista():
    f = _args()
    service = svc()
    data = service.data()
    sessions = {s["sesion_id"]: s for s in service.sessions(data)}
    rows = [dict(r, sesion=sessions[r["sesion_id"]]) for r in data.revisiones if r["sesion_id"] in sessions
            and (not f.get("resultado") or r.get("resultado") == f["resultado"])
            and (not f.get("item") or r.get("item") == f["item"])
            and (not f.get("sesion") or r["sesion_id"] == f["sesion"])]
    summary = {}
    for sid, s in sessions.items():
        items = [r for r in data.revisiones if r["sesion_id"] == sid]
        summary[sid] = {"sesion": s, "total": len(items),
                        "estados": {e: sum(1 for r in items if r.get("resultado") == e)
                                    for e in data.catalogos["estados"]}}
    return render_template("revision.html", rows=rows, summary=summary, f=f, cat=data.catalogos,
                           active="revision")


# --------------------------------------------------------------------------
# Casos de prueba
# --------------------------------------------------------------------------

@bp.route("/pruebas")
def pruebas():
    f = _args()
    service = svc()
    rows = service.all_tests(f)
    page_rows, page, pages = _paginate(rows, int(request.args.get("pagina", 1) or 1))
    data = service.data()
    responsables = sorted({t.get("responsable") for t in data.pruebas if t.get("responsable")})
    return render_template("pruebas.html", rows=page_rows, total=len(rows), page=page, pages=pages, f=f,
                           cat=data.catalogos, responsables=responsables,
                           sesiones=[s["sesion_id"] for s in service.sessions(data)], active="pruebas")


def _test_form(values, errors, test=None, status=200):
    service = svc()
    data = service.data()
    sessions = service.sessions(data, include_examples=True)
    return render_template("prueba_form.html", v=values, errors=errors, test=test, cat=data.catalogos,
                           sesiones=sessions, active="pruebas"), status


@bp.route("/pruebas/nueva", methods=["GET", "POST"])
def prueba_nueva():
    if request.method == "POST":
        try:
            tid = svc().create_test(request.form)
            flash(f"Prueba {tid} registrada.", "ok")
            if request.form.get("accion") == "otra":
                return redirect(url_for("main.prueba_nueva", sesion=request.form.get("sesion_id")))
            return redirect(url_for("main.visita", sid=request.form.get("sesion_id"), tab="pruebas"))
        except ValidationError as exc:
            flash(exc.message, "error")
            return _test_form(request.form, exc.errors, status=422)
        except StoreError as exc:
            resp = _write_errors(exc, url_for("main.pruebas"))
            if resp:
                return resp
            return _test_form(request.form, {}, status=409)
    sid = request.args.get("sesion", "")
    values = {"sesion_id": sid, "estado": S.ESTADO_PENDIENTE}
    if sid:
        s = svc().get_session(sid)
        if s:
            values["responsable"] = s.get("responsable", "")
    return _test_form(values, {})


@bp.route("/pruebas/<tid>/editar", methods=["GET", "POST"])
def prueba_editar(tid):
    data = svc().data()
    test = next((t for t in data.pruebas if t["id"] == tid), None)
    if test is None:
        abort(404)
    if request.method == "POST":
        try:
            svc().update_test(tid, request.form)
            flash(f"Prueba {tid} actualizada.", "ok")
            return redirect(url_for("main.visita", sid=test["sesion_id"], tab="pruebas"))
        except ValidationError as exc:
            flash(exc.message, "error")
            return _test_form(dict(request.form, sesion_id=test["sesion_id"]), exc.errors, test, 422)
        except StoreError as exc:
            resp = _write_errors(exc, url_for("main.visita", sid=test["sesion_id"], tab="pruebas"))
            if resp:
                return resp
            return _test_form(dict(request.form, sesion_id=test["sesion_id"]), {}, test, 409)
    return _test_form(test, {}, test)


# --------------------------------------------------------------------------
# Incidencias
# --------------------------------------------------------------------------

@bp.route("/incidencias")
def incidencias():
    f = _args()
    service = svc()
    rows = service.all_incidents(f)
    page_rows, page, pages = _paginate(rows, int(request.args.get("pagina", 1) or 1))
    data = service.data()
    responsables = sorted({i.get("responsable") for i in data.incidencias if i.get("responsable")})
    return render_template("incidencias.html", rows=page_rows, total=len(rows), page=page, pages=pages, f=f,
                           cat=data.catalogos, responsables=responsables,
                           sesiones=[s["sesion_id"] for s in service.sessions(data)], active="incidencias")


def _incident_form(values, errors, inc=None, status=200):
    service = svc()
    data = service.data()
    sid = values.get("sesion_id") or (inc or {}).get("sesion_id")
    tests = [t for t in data.pruebas if t["sesion_id"] == sid] if sid else []
    history = service.history("Incidencia", inc["id"]) if inc else []
    return render_template("incidencia_form.html", v=values, errors=errors, inc=inc, cat=data.catalogos,
                           sesiones=service.sessions(data, include_examples=True), tests=tests,
                           history=history, active="incidencias"), status


@bp.route("/incidencias/nueva", methods=["GET", "POST"])
def incidencia_nueva():
    if request.method == "POST":
        try:
            iid = svc().create_incident(request.form)
            flash(f"Incidencia {iid} registrada.", "ok")
            return redirect(url_for("main.visita", sid=request.form.get("sesion_id"), tab="incidencias"))
        except ValidationError as exc:
            flash(exc.message, "error")
            return _incident_form(request.form, exc.errors, status=422)
        except StoreError as exc:
            resp = _write_errors(exc, url_for("main.incidencias"))
            if resp:
                return resp
            return _incident_form(request.form, {}, status=409)
    test_id = request.args.get("prueba")
    if test_id:
        values = svc().incident_defaults_from_test(test_id)
        if values is None:
            abort(404)
    else:
        values = {"sesion_id": request.args.get("sesion", ""), "fecha": datetime.now().strftime("%Y-%m-%d"),
                  "estado": S.INCIDENCIA_ABIERTA}
    return _incident_form(values, {})


@bp.route("/incidencias/<iid>/editar", methods=["GET", "POST"])
def incidencia_editar(iid):
    data = svc().data()
    inc = next((i for i in data.incidencias if i["id"] == iid), None)
    if inc is None:
        abort(404)
    if request.method == "POST":
        try:
            svc().update_incident(iid, request.form)
            flash(f"Incidencia {iid} actualizada.", "ok")
            return redirect(url_for("main.incidencia_editar", iid=iid))
        except ValidationError as exc:
            flash(exc.message, "error")
            return _incident_form(dict(request.form, sesion_id=inc["sesion_id"]), exc.errors, inc, 422)
        except StoreError as exc:
            resp = _write_errors(exc, url_for("main.incidencia_editar", iid=iid))
            if resp:
                return resp
            return _incident_form(dict(request.form, sesion_id=inc["sesion_id"]), {}, inc, 409)
    return _incident_form(inc, {}, inc)


@bp.route("/registros/eliminar-ejemplo", methods=["POST"])
def eliminar_ejemplo():
    tipo, rid = request.form.get("tipo"), request.form.get("id", "")
    sid = request.form.get("sesion_id", "")
    if tipo not in ("Prueba", "Incidencia") or request.form.get("confirmar") != "si":
        abort(400)
    try:
        svc().delete_example(tipo, rid)
        flash(f"{tipo} de ejemplo {rid} eliminada. El cambio quedó en el historial.", "ok")
    except StoreError as exc:
        resp = _write_errors(exc)
        if resp:
            return resp
    tab = "pruebas" if tipo == "Prueba" else "incidencias"
    if SESSION_ID_RE.match(sid):
        return redirect(url_for("main.visita", sid=sid, tab=tab))
    return redirect(url_for("main." + tab))


# --------------------------------------------------------------------------
# Cierre de sesión
# --------------------------------------------------------------------------

@bp.route("/cierre")
def cierre_lista():
    service = svc()
    data = service.data()
    rows = []
    for s in service.sessions(data):
        rows.append({"sesion": s, "totales": service.totals(s["sesion_id"], data),
                     "cierre": next((c for c in data.cierres if c["sesion_id"] == s["sesion_id"]), None)})
    rows.sort(key=lambda r: r["sesion"].get("fecha", ""), reverse=True)
    return render_template("cierre_lista.html", rows=rows, active="cierre")


@bp.route("/visitas/<sid>/cierre", methods=["GET", "POST"])
def cierre(sid):
    session = _session_or_404(sid)
    service = svc()
    data = service.data()
    current = next((c for c in data.cierres if c["sesion_id"] == sid), None)
    errors = {}
    status = 200
    if request.method == "POST":
        try:
            service.save_cierre(sid, request.form)
            flash(f"Cierre de la sesión {sid} guardado.", "ok")
            return redirect(url_for("main.cierre", sid=sid))
        except ValidationError as exc:
            flash(exc.message, "error")
            errors, status = exc.errors, 422
        except StoreError as exc:
            resp = _write_errors(exc, url_for("main.cierre", sid=sid))
            if resp:
                return resp
            status = 409
        values = request.form
    else:
        values = dict(current or {})
        values.setdefault("fecha_cierre", datetime.now().strftime("%Y-%m-%d"))
        if not values.get("versiones_cubiertas"):
            values["versiones_cubiertas"] = service.default_versions_text(session)
        if not values.get("pendientes_area"):
            values["pendientes_area"] = service.default_pending_text(sid, data)
    ev = service.evaluate_closure(sid, data)
    excel_totals = service.totals(sid, data, include_examples=True)
    summary = service.email_summary(sid, {"concepto": values.get("concepto"),
                                          "pendientes_area": values.get("pendientes_area")})
    return render_template("cierre_form.html", s=session, v=values, errors=errors, ev=ev,
                           excel_totals=excel_totals, current=current, cat=data.catalogos,
                           owners=service.pending_by_owner(sid, data), summary=summary,
                           criterios=ext()["config"]["cierre"], active="cierre"), status


@bp.route("/visitas/<sid>/resumen.txt")
def resumen_txt(sid):
    _session_or_404(sid)
    return Response(svc().email_summary(sid), mimetype="text/plain; charset=utf-8")


@bp.route("/visitas/<sid>/informe")
def informe(sid):
    _session_or_404(sid)
    service = svc()
    bundle = service.session_bundle(sid)
    data = service.data()
    return render_template("informe.html", b=bundle, totals=service.totals(sid, data),
                           ev=service.evaluate_closure(sid, data), summary=service.email_summary(sid),
                           generado=datetime.now().strftime("%Y-%m-%d %H:%M"))


# --------------------------------------------------------------------------
# Evidencias
# --------------------------------------------------------------------------

@bp.route("/visitas/<sid>/evidencias", methods=["POST"])
def evidencia_subir(sid):
    _session_or_404(sid)
    tipo = request.form.get("tipo_registro", "Visita")
    registro = request.form.get("registro_id", "").strip() or sid
    back = request.form.get("volver") or url_for("main.visita", sid=sid, tab="evidencias")
    if not back.startswith("/") or back.startswith("//"):
        back = url_for("main.visita", sid=sid, tab="evidencias")
    if tipo not in RECORD_TYPES:
        abort(400)
    categoria = request.form.get("categoria") or None
    if categoria and categoria not in UPLOAD_CATEGORIES:
        abort(400)
    descripcion = request.form.get("descripcion", "").strip()
    files = [(categoria, fs.filename, fs.read(), descripcion)
             for fs in request.files.getlist("archivo") if fs and fs.filename]
    if not files:
        flash("Seleccione al menos un archivo.", "error")
        return redirect(back)
    try:
        metas = svc().attach_files(sid, files, tipo, registro)
        flash(f"{len(metas)} archivo(s) guardado(s) en la carpeta {sid}.", "ok")
        for meta in metas:
            if meta["advertencia"]:
                flash(f"{meta['archivo']}: {meta['advertencia']}", "warn")
    except ValidationError as exc:
        flash(" ".join(exc.errors.values()) or exc.message, "error")
    except StoreError as exc:
        resp = _write_errors(exc, back)
        if resp:
            return resp
    return redirect(back)


@bp.route("/archivo/<path:ruta>")
def evidencia_ver(ruta):
    data = svc().data()
    rec = next((e for e in data.evidencias if e["ruta"] == ruta), None)
    if rec is None:
        abort(404)
    path = ext()["evidence"].resolve(ruta)
    if path is None or not path.is_file():
        abort(404)
    tipo = rec.get("tipo_archivo")
    mimetype = None
    if tipo in TEXT_EXTENSIONS:
        mimetype = "text/plain; charset=utf-8"
    # Solo los informes generados por la plataforma se muestran como HTML.
    is_report = tipo == "html" and rec.get("categoria") == CATEGORIA_INFORME
    if tipo == "html" and not is_report:
        mimetype = "text/plain; charset=utf-8"
    inline = tipo in WEB_IMAGE_EXTENSIONS or tipo in TEXT_EXTENSIONS or tipo in ("pdf", "mp4") or is_report
    return send_file(path, as_attachment=not inline, download_name=rec["archivo"], mimetype=mimetype)


# --------------------------------------------------------------------------
# Carpetas de visitas e informes
# --------------------------------------------------------------------------

@bp.route("/carpetas")
def carpetas():
    f = _args()
    return render_template("carpetas.html", rows=svc().folders(f), f=f, active="carpetas")


@bp.route("/carpetas/<sid>")
def carpeta(sid):
    _session_or_404(sid)
    service = svc()
    manager = ext()["evidence"]
    sub = request.args.get("sub", "")
    if sub and sub not in FOLDER_LABELS and sub not in LOG_SUBFOLDERS:
        abort(404)
    vista = "expediente" if request.args.get("vista") == "expediente" else "archivos"
    ctx = report_context(service, sid, lambda ruta: url_for("main.evidencia_ver", ruta=ruta))
    evidencias = ctx["b"]["evidencias"]
    if sub in LOG_SUBFOLDERS:
        shown = [e for e in evidencias if subfolder_of(e) == sub]
    elif sub:
        shown = ctx["groups"][sub]
    else:
        shown = evidencias
    registered = {e["ruta"] for e in evidencias}
    unregistered = manager.unregistered(sid, registered)
    for u in unregistered:
        u["sugerida"] = category_for_path(u["ruta"])
    default_category = {"fotos": "Foto de la máquina", "logs": CATEGORIA_LOG, "videos": "Video",
                        "documentos": "Documento", "otros": "Otro",
                        **SUBFOLDER_CATEGORY}.get(sub, "Foto de la máquina")
    for e in shown:
        e["subcarpeta"] = subfolder_of(e)
    return render_template("carpeta.html", **ctx, sub=sub, vista=vista, unregistered=unregistered,
                           shown=shown, log_subfolders=LOG_SUBFOLDERS,
                           log_counts={k: sum(1 for e in evidencias if subfolder_of(e) == k)
                                       for k in LOG_SUBFOLDERS},
                           categories=UPLOAD_CATEGORIES, default_category=default_category,
                           text_exts=TEXT_EXTENSIONS, folder_path=str(manager.session_dir(sid)),
                           can_open=os.name == "nt", active="carpetas")


@bp.route("/carpetas/<sid>/ver")
def carpeta_ver(sid):
    _session_or_404(sid)
    ruta = request.args.get("ruta", "")
    rec = next((e for e in svc().data().evidencias if e["ruta"] == ruta and e["sesion_id"] == sid), None)
    if rec is None or rec.get("tipo_archivo") not in TEXT_EXTENSIONS:
        abort(404)
    content, truncated = ext()["evidence"].read_text(ruta)
    if content is None:
        abort(404)
    return render_template("carpeta_ver.html", e=rec, content=content, truncated=truncated,
                           sub=subfolder_of(rec), active="carpetas")


@bp.route("/carpetas/<sid>/informe", methods=["POST"])
def carpeta_informe(sid):
    _session_or_404(sid)
    back = url_for("main.carpeta", sid=sid, sub="informes")
    try:
        meta = generate_visit_report(svc(), ext()["evidence"], sid)
        flash(f"Informe generado: {meta['archivo']}", "ok")
    except StoreError as exc:
        resp = _write_errors(exc, back)
        if resp:
            return resp
    nxt = request.form.get("volver", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else back)


@bp.route("/reportes/informe", methods=["POST"])
def reportes_informe():
    sid = request.form.get("sid", "")
    _session_or_404(sid)
    try:
        meta = generate_visit_report(svc(), ext()["evidence"], sid)
        flash(f"Informe generado para {sid}: {meta['archivo']}", "ok")
    except StoreError as exc:
        resp = _write_errors(exc, url_for("main.reportes"))
        if resp:
            return resp
    return redirect(url_for("main.reportes"))


@bp.route("/carpetas/<sid>/descargar")
def carpeta_zip(sid):
    _session_or_404(sid)
    buffer = build_visit_zip(svc(), ext()["evidence"], sid)
    log.info("Carpeta de la visita %s descargada en .zip", sid)
    return send_file(buffer, as_attachment=True, download_name=f"Visita_{sid}_{datetime.now():%Y%m%d}.zip",
                     mimetype="application/zip")


@bp.route("/carpetas/<sid>/abrir", methods=["POST"])
def carpeta_abrir(sid):
    _session_or_404(sid)
    folder = ext()["evidence"].ensure_session_dir(sid)
    if os.name == "nt" and not current_app.config.get("TESTING"):
        os.startfile(str(folder))  # noqa: S606 - carpeta validada dentro de data/evidencias
    flash(f"Carpeta abierta en el Explorador: {folder}", "ok")
    return redirect(url_for("main.carpeta", sid=sid))


@bp.route("/carpetas/<sid>/eliminar", methods=["POST"])
def carpeta_eliminar(sid):
    _session_or_404(sid)
    if request.form.get("confirmar") != "si":
        abort(400)
    back = request.form.get("volver", "")
    if not back.startswith("/") or back.startswith("//"):
        back = url_for("main.carpeta", sid=sid)
    try:
        rec, trash = svc().delete_evidence(sid, request.form.get("id", ""))
        donde = "Se movió a la papelera de la plataforma" if trash else "El archivo ya no estaba en disco"
        flash(f"{rec['archivo']} eliminado de la visita. {donde}.", "ok")
    except ValidationError as exc:
        flash(" ".join(exc.errors.values()) or exc.message, "error")
    except StoreError as exc:
        resp = _write_errors(exc, back)
        if resp:
            return resp
    return redirect(back)


@bp.route("/carpetas/<sid>/registrar", methods=["POST"])
def carpeta_registrar(sid):
    _session_or_404(sid)
    categoria = request.form.get("categoria") or None
    if categoria and categoria not in UPLOAD_CATEGORIES:
        abort(400)
    try:
        meta = svc().register_existing_file(sid, request.form.get("ruta", ""), categoria)
        flash(f"Archivo {meta['archivo']} registrado.", "ok")
    except ValidationError as exc:
        flash(" ".join(exc.errors.values()) or exc.message, "error")
    except StoreError as exc:
        resp = _write_errors(exc, url_for("main.carpeta", sid=sid))
        if resp:
            return resp
    return redirect(url_for("main.carpeta", sid=sid))


# --------------------------------------------------------------------------
# Máquinas, identificación, reportes
# --------------------------------------------------------------------------

@bp.route("/maquinas")
def maquinas():
    return render_template("maquinas.html", groups=svc().machines(), active="maquinas")


@bp.route("/identificacion")
def identificacion():
    f = _args()
    service = svc()
    all_sessions = service.sessions()
    rows = service.filter_sessions(all_sessions, f)
    rows.sort(key=lambda s: s.get("fecha", ""), reverse=True)
    return render_template("identificacion.html", rows=rows, f=f,
                           options=service.filter_options(all_sessions), active="identificacion")


@bp.route("/reportes")
def reportes():
    service = svc()
    sessions = service.sessions()
    data = service.data()
    seriales = sorted({s["serial_pos"] for s in sessions if s.get("serial_pos")
                       and s["serial_pos"] != S.PENDIENTE_CONFIRMAR})
    visibles = {s["sesion_id"] for s in sessions}
    informes = sorted((e for e in data.evidencias if e.get("categoria") == CATEGORIA_INFORME
                       and e["sesion_id"] in visibles), key=lambda e: e.get("fecha", ""), reverse=True)
    return render_template("reportes.html", sessions=sessions, seriales=seriales, informes=informes[:20],
                           options=service.filter_options(sessions), cat=data.catalogos, active="reportes")


@bp.route("/reportes/comparar")
def comparar():
    sids = [s for s in request.args.getlist("s") if SESSION_ID_RE.match(s)][:6]
    if len(sids) < 2:
        flash("Seleccione al menos dos sesiones para comparar.", "warn")
        return redirect(url_for("main.reportes"))
    return render_template("comparar.html", c=svc().compare(sids), sids=sids, active="reportes")


@bp.route("/reportes/exportar", methods=["POST"])
def exportar():
    service = svc()
    f = {k: v.strip() for k, v in request.form.items() if v and v.strip() and k != "_csrf"}
    sessions = service.filter_sessions(service.sessions(), f)
    path = export_workbook(service, sessions, ext()["paths"].exportaciones)
    log.info("Exportación generada: %s (%d sesiones)", path.name, len(sessions))
    return send_file(path, as_attachment=True, download_name=path.name)


# --------------------------------------------------------------------------
# Configuración y respaldos
# --------------------------------------------------------------------------

@bp.route("/configuracion")
def configuracion():
    e = ext()
    data = svc().data()
    log_path = e["paths"].logs / "app.log"
    log_tail = []
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            log_tail = fh.readlines()[-25:]
    return render_template("configuracion.html", cat=data.catalogos, config=e["config"], paths=e["paths"],
                           backups=e["backups"].list(), pending=e["store"].pending(),
                           log_tail=log_tail, clientes_pais=data.clientes_pais, ciudades=data.ciudades,
                           paired=list(S.CATALOG_PAIRS),
                           editable=[c for c in S.CATALOGS if c[0] not in S.CATALOGS_FIXED
                                     and c[0] not in S.CATALOGS_HIDDEN and c[0] not in S.CATALOG_PAIRS],
                           active="configuracion")


@bp.route("/configuracion/catalogo", methods=["POST"])
def catalogo_agregar():
    key = request.form.get("catalogo", "")
    value = " ".join(request.form.get("valor", "").split())
    pais = request.form.get("pais", "").strip()
    if key not in dict(S.CATALOGS) or key in S.CATALOGS_FIXED or key in S.CATALOGS_HIDDEN:
        abort(400)
    if not value or len(value) > 200:
        flash("Escriba un valor de máximo 200 caracteres.", "error")
        return redirect(url_for("main.configuracion"))
    payload = {"catalog": key, "value": value}
    if key in S.CATALOG_PAIRS:
        if pais not in svc().data().catalogos["pais"]:
            flash("Seleccione el país del cliente o de la ciudad.", "error")
            return redirect(url_for("main.configuracion"))
        payload["pair"] = pais
    try:
        ext()["store"].write([("add_catalog_value", payload)], f"Valor de catálogo: {value}")
        flash(f"'{value}' agregado al catálogo {S.CATALOG_LABELS[key]}"
              f"{' (' + pais + ')' if key in S.CATALOG_PAIRS else ''}.", "ok")
    except StoreError as exc:
        resp = _write_errors(exc, url_for("main.configuracion"))
        if resp:
            return resp
    return redirect(url_for("main.configuracion"))


@bp.route("/configuracion/ajustes", methods=["POST"])
def ajustes():
    e = ext()
    config = e["config"]
    form = request.form
    try:
        retener = int(form.get("retener", config["respaldos"]["retener"]))
        intervalo = int(form.get("intervalo", config["respaldos"]["intervalo_minutos"]))
        if not (1 <= retener <= 1000 and 5 <= intervalo <= 10080):
            raise ValueError
    except ValueError:
        flash("Valores de respaldo no válidos (retención 1–1000, intervalo 5–10080 minutos).", "error")
        return redirect(url_for("main.configuracion"))
    config["respaldos"]["retener"] = retener
    config["respaldos"]["intervalo_minutos"] = intervalo
    config["datos"]["excluir_ejemplos"] = form.get("excluir_ejemplos") == "on"
    for key in ("apto_requiere_cero_fallidas", "apto_requiere_cero_bloqueadas", "apto_requiere_cero_pendientes",
                "apto_requiere_cero_incidencias_abiertas", "apto_requiere_revision_fisica_sin_fallos",
                "condiciones_requiere_pendientes_documentados"):
        config["cierre"][key] = form.get(key) == "on"
    componentes = svc().data().catalogos["componente"]
    config["cierre"]["componentes_criticos"] = [c for c in form.getlist("componentes_criticos") if c in componentes]
    config["pruebas"]["exigir_evidencia_para_aprobar"] = form.get("exigir_evidencia_para_aprobar") == "on"
    save_config(e["base_dir"], config)
    log.info("Configuración actualizada.")
    flash("Configuración guardada.", "ok")
    return redirect(url_for("main.configuracion"))


@bp.route("/respaldos/crear", methods=["POST"])
def respaldo_crear():
    try:
        name = ext()["backups"].create("manual")
        flash(f"Respaldo creado: {name}", "ok")
    except StoreError as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.configuracion"))


@bp.route("/respaldos/restaurar", methods=["POST"])
def respaldo_restaurar():
    name = request.form.get("nombre", "")
    if request.form.get("confirmar") != "si":
        abort(400)
    try:
        previous = ext()["backups"].restore(name, ext()["store"])
        flash(f"Respaldo {name} restaurado. El estado anterior quedó en {previous}.", "ok")
    except StoreError as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.configuracion"))


@bp.route("/respaldos/descargar/<name>")
def respaldo_descargar(name):
    try:
        path = ext()["backups"].path_of(name)
    except StoreError:
        abort(404)
    return send_file(path, as_attachment=True, download_name=name)


@bp.route("/pendientes/reintentar", methods=["POST"])
def pendientes_reintentar():
    try:
        n = ext()["store"].retry_pending()
        flash(f"Se guardaron {n} cambio(s) pendiente(s) en el libro." if n else "No hay cambios pendientes.", "ok")
    except ExcelLockedError as exc:
        flash(f"Siguen sin guardarse: {exc}", "warn")
    except StoreError as exc:
        flash(f"No se pudieron aplicar los cambios pendientes: {exc}", "error")
    return redirect(request.form.get("volver") if (request.form.get("volver") or "").startswith("/")
                    else url_for("main.dashboard"))


@bp.app_errorhandler(404)
def _404(e):
    return render_template("error.html", code=404, message="La página o el registro solicitado no existe."), 404


@bp.app_errorhandler(400)
def _400(e):
    return render_template("error.html", code=400,
                           message=getattr(e, "description", None) or "Solicitud no válida."), 400


@bp.app_errorhandler(413)
def _413(e):
    return render_template("error.html", code=413, message="El archivo supera el tamaño máximo permitido."), 413


@bp.app_errorhandler(StoreError)
def _store_error(e):
    log.error("Error de almacenamiento: %s", e)
    return render_template("error.html", code=500, message=str(e)), 500
