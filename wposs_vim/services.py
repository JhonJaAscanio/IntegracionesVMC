"""Lógica de negocio: sesiones, revisiones, pruebas, incidencias y cierre."""
import json
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime

from . import schema as S
from . import validators as V
from .excel_store import ConflictError, PendingWriteError
from .validators import ValidationError

INTEGRATION_CATEGORIES = OrderedDict([
    ("aprobada", "Apto para piloto"),
    ("condiciones", "Apto con condiciones"),
    ("pendiente", "Pendiente"),
    ("fallida", "No apto"),
])


def _has_marker(rec):
    return any(S.EXAMPLE_MARKER in str(v).casefold() for k, v in rec.items() if k != "_row")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


class Service:
    def __init__(self, store, config, evidence=None):
        self.store = store
        self.config = config
        self.evidence = evidence

    # ------------------------------------------------------------------
    # Lectura y enriquecimiento
    # ------------------------------------------------------------------
    @property
    def exclude_examples(self):
        return bool(self.config["datos"].get("excluir_ejemplos", True))

    def data(self):
        return self.store.read()

    def example_sessions(self, data):
        return {s["sesion_id"] for s in data.sesiones
                if S.EXAMPLE_MARKER in s.get("observaciones", "").casefold()}

    def _is_example_incident(self, inc, examples):
        return inc["sesion_id"] in examples or S.EXAMPLE_MARKER in inc.get("descripcion", "").casefold()

    def sessions(self, data=None, include_examples=None):
        data = data or self.data()
        if include_examples is None:
            include_examples = not self.exclude_examples
        examples = self.example_sessions(data)
        cierres = {c["sesion_id"]: c for c in data.cierres}
        tests_by = defaultdict(list)
        for t in data.pruebas:
            tests_by[t["sesion_id"]].append(t)
        incs_by = defaultdict(list)
        for i in data.incidencias:
            if include_examples or not self._is_example_incident(i, examples):
                incs_by[i["sesion_id"]].append(i)
        result = []
        for s in data.sesiones:
            sid = s["sesion_id"]
            es_ejemplo = sid in examples
            if es_ejemplo and not include_examples:
                continue
            meta = data.meta.get(sid, {})
            cierre = cierres.get(sid)
            concepto = (cierre or {}).get("concepto", "")
            tests = tests_by.get(sid, [])
            rec = dict(s)
            rec.update({
                "es_ejemplo": es_ejemplo,
                "estado_registro": meta.get("estado_registro", S.ESTADO_REGISTRO_EN_CURSO),
                "creado": meta.get("creado", ""),
                "modificado": meta.get("modificado", ""),
                "origen": meta.get("origen", ""),
                "concepto": concepto,
                "categoria": self.category(concepto),
                "n_pruebas": len(tests),
                "n_abiertas_pruebas": sum(1 for t in tests if t.get("estado") in
                                          (S.ESTADO_FALLIDO, S.ESTADO_PENDIENTE, S.ESTADO_BLOQUEADO, "")),
                "n_fallidas": sum(1 for t in tests if t.get("estado") == S.ESTADO_FALLIDO),
                "n_pendientes": sum(1 for t in tests if t.get("estado") in (S.ESTADO_PENDIENTE, "")),
                "inc_abiertas": sum(1 for i in incs_by.get(sid, [])
                                    if i.get("estado") and i.get("estado") != S.INCIDENCIA_CERRADA),
            })
            rec["estado_integracion"] = concepto or rec["estado_registro"]
            rec["cliente_label"] = self.client_label(rec)
            rec["raiz"] = rec.get("sesion_origen") or sid
            rec["numero"] = self._orden(rec.get("numero_visita")) or 1
            rec["es_seguimiento"] = bool(rec.get("sesion_origen"))
            result.append(rec)
        return result

    @staticmethod
    def category(concepto):
        return {
            S.CONCEPTO_APTO: "aprobada",
            S.CONCEPTO_CONDICIONES: "condiciones",
            S.CONCEPTO_NO_APTO: "fallida",
        }.get(concepto, "pendiente")

    def get_session(self, sid, data=None):
        data = data or self.data()
        for s in self.sessions(data, include_examples=True):
            if s["sesion_id"] == sid:
                return s
        return None

    def session_bundle(self, sid):
        data = self.data()
        session = self.get_session(sid, data)
        if session is None:
            return None
        examples = self.example_sessions(data)
        return {
            "sesion": session,
            "revisiones": [r for r in data.revisiones if r["sesion_id"] == sid],
            "pruebas": [t for t in data.pruebas if t["sesion_id"] == sid],
            "incidencias": [dict(i, es_ejemplo=self._is_example_incident(i, examples))
                            for i in data.incidencias if i["sesion_id"] == sid],
            "cierre": next((c for c in data.cierres if c["sesion_id"] == sid), None),
            "evidencias": [e for e in data.evidencias if e["sesion_id"] == sid],
            "historial": [h for h in data.historial if h["sesion_id"] == sid],
            "checklist": self.session_checklist(sid, data),
            "serie": self.series(session["raiz"], data),
            "serie_checklist": {v["sesion_id"]: self.session_checklist(v["sesion_id"], data)
                                for v in self.series(session["raiz"], data)},
            "pendientes_serie": self.series_pending(session["raiz"], data),
            "trabajo_serie": self.series_open_work(session["raiz"], data),
        }

    # ------------------------------------------------------------------
    # Identificadores
    # ------------------------------------------------------------------
    def next_id(self, prefix, data=None):
        data = data or self.data()
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        numbers = [0]
        for rows, key in ((data.sesiones, "sesion_id"), (data.pruebas, "id"),
                          (data.incidencias, "id"), (data.evidencias, "id"), (data.checklist, "id")):
            for rec in rows:
                m = pattern.match(rec.get(key, ""))
                if m:
                    numbers.append(int(m.group(1)))
        if data.contadores.get(prefix):
            try:
                numbers.append(int(data.contadores[prefix]))
            except ValueError:
                pass
        # IDs reservados por cambios aún pendientes de escribir.
        text_pattern = re.compile(rf"\b{re.escape(prefix)}-(\d+)\b")
        for item in self.store.pending():
            for m in text_pattern.finditer(json.dumps(item.get("ops", []), ensure_ascii=False)):
                numbers.append(int(m.group(1)))
        return f"{prefix}-{max(numbers) + 1:03d}"

    def test_prefix(self, componente):
        prefixes = self.config["pruebas"]["prefijos"]
        if componente in prefixes:
            return prefixes[componente]
        letters = re.sub(r"[^A-Z]", "", componente.upper()
                         .translate(str.maketrans("ÁÉÍÓÚÑ", "AEIOUN")))
        return (letters[:3] or "OTR").ljust(3, "X")

    # ------------------------------------------------------------------
    # Sesiones
    # ------------------------------------------------------------------
    def _ensure_catalog_ops(self, data, catalog, value):
        if value and value != S.PENDIENTE_CONFIRMAR and value not in data.catalogos.get(catalog, []):
            return [("add_catalog_value", {"catalog": catalog, "value": value})]
        return []

    @staticmethod
    def _ensure_city_ops(data, values):
        """Una ciudad escrita a mano se unifica con la del catálogo del país (sin distinguir
        mayúsculas) o, si es nueva, se agrega al catálogo emparejada con su país."""
        ciudad, pais = values.get("ciudad", ""), values.get("pais", "")
        if not ciudad or not pais:
            return []
        for known in data.ciudades.get(pais, []):
            if known.casefold() == ciudad.casefold():
                values["ciudad"] = known
                return []
        return [("add_catalog_value", {"catalog": "ciudad", "value": ciudad, "pair": pais})]

    def create_session(self, form, draft=False, files=None):
        """Crea la sesión y, en la misma escritura, registra los archivos adjuntos.

        files: lista de (categoría, nombre de archivo, contenido, descripción).
        """
        with self.store._lock:
            data = self.data()
            values = V.clean(form, V.SESSION_FIELDS)
            errors = {}
            try:
                V.validate_session(values, data.catalogos, draft, data.ciudades)
            except ValidationError as exc:
                errors.update(exc.errors)
            root = None
            if values.get("sesion_origen"):
                origin = self.get_session(values["sesion_origen"], data)
                if origin is None:
                    errors["sesion_origen"] = "La visita de origen no existe."
                else:
                    root = origin["raiz"]
            checklist = []
            try:
                checklist = V.parse_checklist_results(
                    form, self.visit_checklist_items(values.get("tipo_prueba", ""), root, data,
                                                     include_pending=form.get("incluir_pendientes") != "no"),
                    data.catalogos.get("resultado_prueba", []))
            except ValidationError as exc:
                errors.update(exc.errors)
            if errors:
                raise ValidationError(errors)
            self._validate_files(files or [])
            sid = self.next_id("SES", data)
            if any(s["sesion_id"] == sid for s in data.sesiones):
                raise ConflictError("No se pudo generar un Sesión ID único.")
            values["sesion_id"] = sid
            values["sesion_origen"] = root or ""
            values["numero_visita"] = (max(s["numero"] for s in self.series(root, data)) + 1) if root else 1
            estado = S.ESTADO_REGISTRO_BORRADOR if draft else S.ESTADO_REGISTRO_EN_CURSO
            ops = self._ensure_catalog_ops(data, "fabricante", values.get("fabricante"))
            ops += self._ensure_city_ops(data, values)
            ops.append(("create_session", {"sesion": values, "estado_registro": estado}))
            if checklist:
                ops.append(("checklist_set_results", {"sesion_id": sid, "items": checklist}))
            if self.evidence:
                self.evidence.ensure_session_dir(sid)
            metas = self._store_files(sid, files or [], "Visita", sid, data)
            ops += [("add_evidence", {"evidencia": m}) for m in metas]
            self._write_with_files(ops, f"Nueva sesión {sid}", metas)
            return sid

    # ------------------------------------------------------------------
    # Checklist de integración
    # ------------------------------------------------------------------
    @staticmethod
    def _orden(value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def checklist_items(self, tipo, data=None, include_inactive=False):
        """Ítems de la plantilla de un tipo de prueba, ordenados por sección y orden."""
        data = data or self.data()
        rows = [r for r in data.checklist if r["tipo"] == tipo
                and (include_inactive or r.get("activo") != S.CHECKLIST_INACTIVO)]
        section_order = []
        for r in rows:
            if r["seccion"] not in section_order:
                section_order.append(r["seccion"])
        return sorted(rows, key=lambda r: (section_order.index(r["seccion"]), self._orden(r["orden"]), r["id"]))

    @staticmethod
    def group_sections(items):
        """[(sección, [ítems])] conservando el orden de aparición."""
        groups = OrderedDict()
        for item in items:
            groups.setdefault(item["seccion"], []).append(item)
        return list(groups.items())

    def checklist_templates(self, data=None):
        """{tipo de prueba: [(sección, [ítems activos])]} para el formulario de visita."""
        data = data or self.data()
        return {tipo: self.group_sections(self.checklist_items(tipo, data))
                for tipo in data.catalogos.get("tipo_prueba", [])}

    def session_checklist(self, sid, data=None):
        """Resultados del checklist de una visita, agrupados por sección, y su resumen."""
        data = data or self.data()
        rows = [r for r in data.checklist_res if r["sesion_id"] == sid]
        section_order = []
        for r in rows:
            if r["seccion"] not in section_order:
                section_order.append(r["seccion"])
        rows.sort(key=lambda r: (section_order.index(r["seccion"]), self._orden(r["orden"])))
        counts = Counter(r.get("resultado") or "Sin marcar" for r in rows)
        return {"secciones": self.group_sections(rows), "total": len(rows), "conteo": dict(counts),
                "exitosas": counts.get("Exitosa", 0), "fallidas": counts.get(S.RESULTADO_FALLIDA, 0),
                "sin_marcar": counts.get("Sin marcar", 0)}

    def missing_checklist_items(self, sid, data=None):
        """Ítems activos de la plantilla del tipo de la visita que aún no tiene la visita."""
        data = data or self.data()
        session = self.get_session(sid, data)
        if session is None:
            return []
        present = {r["item_id"] for r in data.checklist_res if r["sesion_id"] == sid}
        return [i for i in self.checklist_items(session.get("tipo_prueba", ""), data) if i["id"] not in present]

    def save_session_checklist(self, sid, form):
        """Guarda los resultados marcados en la pestaña Checklist de la visita."""
        with self.store._lock:
            data = self.data()
            rows = [r for r in data.checklist_res if r["sesion_id"] == sid]
            if not rows:
                raise ValidationError({}, "La visita no tiene checklist cargado.")
            entries = V.parse_checklist_results(form, rows, data.catalogos.get("resultado_prueba", []))
            self.store.write([("checklist_set_results", {"sesion_id": sid, "items": entries})],
                             f"Checklist de {sid}")

    def load_session_checklist(self, sid):
        """Agrega a la visita los ítems de la plantilla de su tipo que todavía no tiene."""
        with self.store._lock:
            data = self.data()
            missing = self.missing_checklist_items(sid, data)
            if not missing:
                return 0
            entries = [{"item_id": i["id"], "tipo": i["tipo"], "seccion": i["seccion"], "orden": i["orden"],
                        "texto": i["texto"], "resultado": "", "observacion": ""} for i in missing]
            self.store.write([("checklist_set_results", {"sesion_id": sid, "items": entries})],
                             f"Checklist cargado en {sid}")
            return len(entries)

    def add_checklist_item(self, form):
        with self.store._lock:
            data = self.data()
            values = V.clean(form, ["tipo", "seccion", "seccion_nueva", "texto"])
            values["seccion"] = values.pop("seccion_nueva") or values["seccion"]
            V.validate_checklist_item(values, data.catalogos.get("tipo_prueba", []))
            same = [r for r in data.checklist if r["tipo"] == values["tipo"] and r["seccion"] == values["seccion"]]
            values.update({"id": self.next_id("CHK", data), "activo": S.CHECKLIST_ACTIVO,
                           "orden": max((self._orden(r["orden"]) for r in same), default=0) + 1})
            self.store.write([("checklist_add_item", {"item": values})], f"Ítem de checklist {values['id']}")
            return values["id"]

    def update_checklist_item(self, item_id, form):
        with self.store._lock:
            data = self.data()
            current = next((r for r in data.checklist if r["id"] == item_id), None)
            if current is None:
                raise ConflictError(f"El ítem {item_id} no existe.")
            values = V.clean(form, ["seccion", "texto"])
            values["tipo"] = current["tipo"]
            V.validate_checklist_item(values, data.catalogos.get("tipo_prueba", []) + [current["tipo"]])
            fields = {"seccion": values["seccion"], "texto": values["texto"]}
            if values["seccion"] != current["seccion"]:
                same = [r for r in data.checklist if r["tipo"] == current["tipo"] and r["seccion"] == values["seccion"]]
                fields["orden"] = max((self._orden(r["orden"]) for r in same), default=0) + 1
            self.store.write([("checklist_update_item", {"id": item_id, "fields": fields})],
                             f"Edición del ítem {item_id}")

    def set_checklist_item_active(self, item_id, active):
        with self.store._lock:
            data = self.data()
            if not any(r["id"] == item_id for r in data.checklist):
                raise ConflictError(f"El ítem {item_id} no existe.")
            value = S.CHECKLIST_ACTIVO if active else S.CHECKLIST_INACTIVO
            self.store.write([("checklist_update_item", {"id": item_id, "fields": {"activo": value},
                                                         "accion": "Ítem restaurado" if active else "Ítem quitado"})],
                             f"Ítem {item_id} {'restaurado' if active else 'quitado'}")

    def move_checklist_item(self, item_id, direction):
        """Sube o baja un ítem dentro de su sección."""
        with self.store._lock:
            data = self.data()
            item = next((r for r in data.checklist if r["id"] == item_id), None)
            if item is None:
                raise ConflictError(f"El ítem {item_id} no existe.")
            siblings = [r for r in self.checklist_items(item["tipo"], data, include_inactive=True)
                        if r["seccion"] == item["seccion"]]
            ids = [r["id"] for r in siblings]
            i = ids.index(item_id)
            j = i - 1 if direction == "subir" else i + 1
            if not 0 <= j < len(ids):
                return
            ids[i], ids[j] = ids[j], ids[i]
            self.store.write([("checklist_reorder", {"tipo": item["tipo"], "seccion": item["seccion"], "ids": ids})],
                             f"Orden del checklist {item['tipo']}")

    # ------------------------------------------------------------------
    # Integración: visita de origen y visitas de seguimiento
    # ------------------------------------------------------------------
    def series(self, root, data=None):
        """Visitas de una integración (origen y seguimientos) ordenadas por número de visita."""
        data = data or self.data()
        visits = [s for s in self.sessions(data, include_examples=True) if s["raiz"] == root]
        return sorted(visits, key=lambda s: (s["numero"], s.get("fecha", ""), s["sesion_id"]))

    def series_pending(self, root, data=None):
        """Pasos de checklist que la serie aún no resolvió (último resultado distinto de Exitosa/No aplica)."""
        data = data or self.data()
        latest = OrderedDict()
        for visit in self.series(root, data):
            rows = [r for r in data.checklist_res if r["sesion_id"] == visit["sesion_id"]]
            rows.sort(key=lambda r: self._orden(r.get("orden")))
            for r in rows:
                latest[r["item_id"]] = dict(r, visita=visit["sesion_id"], numero=visit["numero"])
        return [r for r in latest.values() if r.get("resultado") not in S.CHECKLIST_RESUELTOS]

    def series_open_work(self, root, data=None):
        """Pruebas sin aprobar e incidencias abiertas de todas las visitas de la integración."""
        data = data or self.data()
        sids = {s["sesion_id"] for s in self.series(root, data)}
        examples = self.example_sessions(data)
        pruebas = [t for t in data.pruebas if t["sesion_id"] in sids and t.get("estado") in
                   (S.ESTADO_FALLIDO, S.ESTADO_BLOQUEADO, S.ESTADO_PENDIENTE, "")]
        incidencias = [i for i in data.incidencias if i["sesion_id"] in sids and i.get("estado")
                       and i["estado"] != S.INCIDENCIA_CERRADA and not self._is_example_incident(i, examples)]
        return {"pruebas": pruebas, "incidencias": incidencias}

    def visit_checklist_items(self, tipo, root=None, data=None, include_pending=True):
        """Ítems del checklist de una visita nueva: pendientes heredados de la serie y plantilla del tipo."""
        data = data or self.data()
        pending = []
        if root and include_pending:
            for r in self.series_pending(root, data):
                pending.append({"id": r["item_id"], "tipo": r.get("tipo", ""), "seccion": S.SECCION_PENDIENTES,
                                "orden": str(len(pending) + 1), "texto": r["texto"],
                                "anterior": r.get("resultado") or "Sin marcar", "visita": r["visita"]})
        seen = {i["id"] for i in pending}
        return pending + [i for i in self.checklist_items(tipo, data) if i["id"] not in seen]

    def followup_defaults(self, origin_sid, data=None):
        """Valores precargados para una visita de seguimiento: datos de la última visita de la serie."""
        data = data or self.data()
        origin = self.get_session(origin_sid, data)
        if origin is None:
            return None
        last = self.series(origin["raiz"], data)[-1]
        values = {k: last.get(k, "") for k in S.FOLLOWUP_COPY_FIELDS}
        now = datetime.now()
        tipo = S.TIPO_SEGUIMIENTO if S.TIPO_SEGUIMIENTO in data.catalogos.get("tipo_prueba", []) else ""
        values.update({"fecha": now.strftime("%Y-%m-%d"), "hora": now.strftime("%H:%M"), "tipo_prueba": tipo,
                       "objetivo": self.objective_templates().get(tipo, ""), "sesion_origen": origin["raiz"]})
        return values

    # ------------------------------------------------------------------
    # Evidencias y carpetas de visita
    # ------------------------------------------------------------------
    def _validate_files(self, files):
        errors = []
        for categoria, filename, content, _ in files:
            try:
                self.evidence.validate(filename, content, categoria)
            except ValidationError as exc:
                errors.extend(exc.errors.values())
        if errors:
            raise ValidationError({"archivos": " ".join(errors)},
                                  "Revise los archivos adjuntos. Vuelva a seleccionarlos antes de guardar.")

    def _store_files(self, sid, files, tipo, registro_id, data):
        """Guarda los archivos en disco y devuelve sus metadatos con IDs consecutivos."""
        if not files:
            return []
        first = int(self.next_id("EVD", data).split("-")[1])
        metas = []
        try:
            for i, (categoria, filename, content, descripcion) in enumerate(files):
                meta = self.evidence.store(sid, registro_id, filename, content, categoria)
                meta.update({"id": f"EVD-{first + i:03d}", "sesion_id": sid, "tipo_registro": tipo,
                             "registro_id": registro_id, "descripcion": (descripcion or "")[:500]})
                metas.append(meta)
        except Exception:
            for meta in metas:
                self.evidence.remove_file(meta["ruta"])
            raise
        return metas

    def _write_with_files(self, ops, descripcion, metas):
        """Escribe; si falla (salvo diferido por bloqueo) elimina los archivos recién guardados."""
        try:
            self.store.write(ops, descripcion)
        except PendingWriteError:
            raise
        except Exception:
            for meta in metas:
                self.evidence.remove_file(meta["ruta"])
            raise

    def attach_files(self, sid, files, tipo="Visita", registro_id=None):
        """Adjunta uno o varios archivos a la visita o a uno de sus registros."""
        with self.store._lock:
            data = self.data()
            if not any(s["sesion_id"] == sid for s in data.sesiones):
                raise ConflictError(f"La sesión {sid} no existe.")
            if not files:
                raise ValidationError({"archivos": "Seleccione al menos un archivo."},
                                      "Seleccione al menos un archivo.")
            self._validate_files(files)
            registro_id = registro_id if tipo != "Visita" and registro_id else sid
            metas = self._store_files(sid, files, tipo, registro_id, data)
            self._write_with_files([("add_evidence", {"evidencia": m}) for m in metas],
                                   f"{len(metas)} evidencia(s) en {sid}", metas)
            return metas

    def delete_evidence(self, sid, evidence_id):
        """Elimina una evidencia de la visita: mueve el archivo a la papelera y quita su registro.

        Si la escritura falla (salvo diferida por bloqueo), el archivo vuelve a su lugar.
        Devuelve (registro eliminado, ruta del archivo en la papelera o None).
        """
        with self.store._lock:
            data = self.data()
            rec = next((e for e in data.evidencias if e["id"] == evidence_id), None)
            if rec is None or rec["sesion_id"] != sid:
                raise ConflictError("La evidencia no existe en esta visita.")
            trash = self.evidence.move_to_trash(sid, rec["ruta"])
            trash_rel = (trash.relative_to(self.evidence.base.parent).as_posix() if trash
                         else "archivo no encontrado en disco")
            try:
                self.store.write([("delete_evidence", {"id": evidence_id, "sesion_id": sid,
                                                       "papelera": trash_rel})],
                                 f"Eliminación de la evidencia {evidence_id} de {sid}")
            except PendingWriteError:
                raise
            except Exception:
                self.evidence.restore_from_trash(trash, rec["ruta"])
                raise
            return rec, trash

    def register_existing_file(self, sid, rel_path, categoria=None):
        """Registra un archivo copiado manualmente a la carpeta de la visita."""
        with self.store._lock:
            data = self.data()
            if any(e["ruta"] == rel_path for e in data.evidencias):
                raise ConflictError("El archivo ya está registrado.")
            meta = self.evidence.register_existing(sid, rel_path, categoria)
            meta.update({"id": self.next_id("EVD", data), "sesion_id": sid, "tipo_registro": "Visita",
                         "registro_id": sid, "descripcion": "Registrado desde la carpeta de la visita"})
            self.store.write([("add_evidence", {"evidencia": meta})], f"Registro de archivo en {sid}")
            return meta

    def save_report(self, sid, filename, html):
        """Guarda un informe HTML generado en la carpeta informes/ y lo registra."""
        with self.store._lock:
            data = self.data()
            meta = self.evidence.store_generated(sid, filename, html.encode("utf-8"))
            meta.update({"id": self.next_id("EVD", data), "sesion_id": sid, "tipo_registro": "Visita",
                         "registro_id": sid, "descripcion": "Informe de visita generado por la plataforma"})
            self._write_with_files([("add_evidence", {"evidencia": meta})], f"Informe de {sid}", [meta])
            return meta

    def folders(self, f=None):
        """Resumen de la carpeta de cada visita: archivos por subcarpeta y última actividad."""
        from .evidence import FOLDERS, folder_of
        data = self.data()
        sessions = self.filter_sessions(self.sessions(data), f or {})
        by_session = defaultdict(list)
        for e in data.evidencias:
            by_session[e["sesion_id"]].append(e)
        result = []
        for s in sessions:
            evs = by_session.get(s["sesion_id"], [])
            counts = Counter(folder_of(e) for e in evs)
            result.append({"sesion": s, "total": len(evs),
                           "conteo": {k: counts.get(k, 0) for k in FOLDERS},
                           "ultima": max((e.get("fecha", "") for e in evs), default="")})
        result.sort(key=lambda r: (r["sesion"].get("fecha", ""), r["sesion"]["sesion_id"]), reverse=True)
        return result

    def update_session(self, sid, form, draft=False):
        with self.store._lock:
            data = self.data()
            session = self.get_session(sid, data)
            if session is None:
                raise ConflictError(f"La sesión {sid} no existe.")
            values = V.clean(form, V.SESSION_FIELDS)
            # Los campos que el formulario ya no solicita conservan su valor actual.
            for key in S.ID_LEGACY_FIELDS:
                if key not in form:
                    values[key] = session.get(key, "")
            for key in S.ID_SERIES_FIELDS:
                values[key] = session.get(key, "")
            V.validate_session(values, data.catalogos, draft, data.ciudades, current=session)
            estado = None
            if session["estado_registro"] == S.ESTADO_REGISTRO_BORRADOR and not draft:
                estado = S.ESTADO_REGISTRO_EN_CURSO
            ops = self._ensure_catalog_ops(data, "fabricante", values.get("fabricante"))
            ops += self._ensure_city_ops(data, values)
            ops.append(("update_session", {"sesion_id": sid, "fields": values, "estado_registro": estado}))
            self.store.write(ops, f"Edición de la sesión {sid}")

    # ------------------------------------------------------------------
    # Revisión física y eléctrica
    # ------------------------------------------------------------------
    def init_revision(self, sid, extra_item=None):
        data = self.data()
        items = list(data.catalogos.get("item_revision", []))
        if extra_item:
            extra_item = extra_item.strip()
            if len(extra_item) > 300:
                raise ValidationError({"item": "Máximo 300 caracteres."})
            items = [extra_item]
        self.store.write([("init_revision", {"sesion_id": sid, "items": items})],
                         f"Revisión física de {sid}")

    def update_revision(self, sid, form):
        data = self.data()
        rows = [r for r in data.revisiones if r["sesion_id"] == sid]
        estados = data.catalogos["estados"]
        items, errors = [], {}
        for i, rec in enumerate(rows):
            resultado = (form.get(f"resultado_{i}") or "").strip()
            obs = (form.get(f"observaciones_{i}") or "").replace("\r\n", "\n").strip()
            if form.get(f"item_{i}") != rec["item"]:
                raise ConflictError("La revisión cambió mientras se editaba. Recargue la página.")
            if resultado and resultado not in estados:
                errors[f"resultado_{i}"] = "Valor no válido."
            if len(obs) > V.MAX_TEXT:
                errors[f"observaciones_{i}"] = "Texto demasiado largo."
            items.append({"item": rec["item"], "resultado": resultado, "observaciones": obs})
        if errors:
            raise ValidationError(errors)
        self.store.write([("update_revision", {"sesion_id": sid, "items": items})],
                         f"Resultados de revisión física de {sid}")

    # ------------------------------------------------------------------
    # Casos de prueba
    # ------------------------------------------------------------------
    def create_test(self, form):
        with self.store._lock:
            data = self.data()
            values = V.clean(form, V.TEST_FIELDS)
            V.validate_test(values, data.catalogos, self.config)
            if not any(s["sesion_id"] == values["sesion_id"] for s in data.sesiones):
                raise ValidationError({"sesion_id": "La sesión no existe."})
            values["id"] = self.next_id(self.test_prefix(values["componente"]), data)
            self.store.write([("create_test", {"prueba": values})], f"Nueva prueba {values['id']}")
            return values["id"]

    def update_test(self, test_id, form):
        with self.store._lock:
            data = self.data()
            current = next((t for t in data.pruebas if t["id"] == test_id), None)
            if current is None:
                raise ConflictError(f"La prueba {test_id} no existe.")
            values = V.clean(form, [k for k in V.TEST_FIELDS if k != "sesion_id"])
            values["sesion_id"] = current["sesion_id"]
            has_ev = bool(current.get("evidencia"))
            V.validate_test(values, data.catalogos, self.config, has_evidence=has_ev)
            self.store.write([("update_test", {"id": test_id, "fields": values})],
                             f"Edición de la prueba {test_id}")

    # ------------------------------------------------------------------
    # Incidencias
    # ------------------------------------------------------------------
    def incident_defaults_from_test(self, test_id):
        """Datos precargados para crear una incidencia desde una prueba."""
        data = self.data()
        test = next((t for t in data.pruebas if t["id"] == test_id), None)
        if test is None:
            return None
        session = next((s for s in data.sesiones if s["sesion_id"] == test["sesion_id"]), {})
        version_key = {
            "POS NEW5320": "firmware", "MDB": "mdb_version", "Financiera": "version_financiera",
            "Agente Polaris": "version_polaris",
        }.get(test["componente"])
        version = session.get(version_key, "") if version_key else ""
        comp = f"{test['componente']} {version}".strip() if version else test["componente"]
        return {
            "sesion_id": test["sesion_id"], "prueba_id": test_id, "fecha": _today(),
            "componente_version": comp, "pasos": test.get("procedimiento", ""),
            "resultado_esperado": test.get("resultado_esperado", ""),
            "resultado_obtenido": test.get("resultado_obtenido", ""),
            "responsable": test.get("responsable", ""), "estado": S.INCIDENCIA_ABIERTA,
            "descripcion": f"{test_id}: {test.get('objetivo', '')}",
        }

    def create_incident(self, form):
        with self.store._lock:
            data = self.data()
            values = V.clean(form, V.INCIDENT_FIELDS)
            V.validate_incident(values, data.catalogos)
            if not any(s["sesion_id"] == values["sesion_id"] for s in data.sesiones):
                raise ValidationError({"sesion_id": "La sesión no existe."})
            if values.get("prueba_id"):
                test = next((t for t in data.pruebas if t["id"] == values["prueba_id"]), None)
                if test is None or test["sesion_id"] != values["sesion_id"]:
                    raise ValidationError({"prueba_id": "La prueba no existe en esta sesión."})
            values["id"] = self.next_id("INC", data)
            self.store.write([("create_incident", {"incidencia": values})], f"Nueva incidencia {values['id']}")
            return values["id"]

    def update_incident(self, inc_id, form):
        with self.store._lock:
            data = self.data()
            current = next((i for i in data.incidencias if i["id"] == inc_id), None)
            if current is None:
                raise ConflictError(f"La incidencia {inc_id} no existe.")
            values = V.clean(form, [k for k in V.INCIDENT_FIELDS if k != "sesion_id"])
            values["sesion_id"] = current["sesion_id"]
            V.validate_incident(values, data.catalogos)
            accion = "Edición"
            if values.get("estado") != current.get("estado"):
                accion = f"Cambio de estado: {current.get('estado') or '—'} → {values.get('estado')}"
            self.store.write([("update_incident", {"id": inc_id, "fields": values, "accion": accion})],
                             f"Edición de la incidencia {inc_id}")

    def delete_example(self, tipo, record_id):
        self.store.write([("delete_example", {"tipo": tipo, "id": record_id})],
                         f"Eliminación de fila de ejemplo {record_id}")

    # ------------------------------------------------------------------
    # Cierre de sesión
    # ------------------------------------------------------------------
    def totals(self, sid, data=None, include_examples=None):
        """Equivalente en Python de las fórmulas S:Y de 'Cierre de Sesión'."""
        data = data or self.data()
        if include_examples is None:
            include_examples = not self.exclude_examples
        examples = self.example_sessions(data)
        tests = [t for t in data.pruebas if t["sesion_id"] == sid]
        if not include_examples and sid in examples:
            tests = []
        estados = Counter(t.get("estado", "") for t in tests)
        incs = [i for i in data.incidencias if i["sesion_id"] == sid
                and (include_examples or not self._is_example_incident(i, examples))]
        return {
            "planificadas": len(tests),
            # Igual que la fórmula: todo estado distinto de "Pendiente" y de vacío.
            "ejecutadas": sum(n for e, n in estados.items() if e not in (S.ESTADO_PENDIENTE, "")),
            "aprobadas": estados.get(S.ESTADO_APROBADO, 0),
            "fallidas": estados.get(S.ESTADO_FALLIDO, 0),
            "bloqueadas": estados.get(S.ESTADO_BLOQUEADO, 0),
            "pendientes": estados.get(S.ESTADO_PENDIENTE, 0),
            "sin_estado": estados.get("", 0),
            "otros": {e: n for e, n in estados.items()
                      if e not in ("", S.ESTADO_APROBADO, S.ESTADO_FALLIDO,
                                   S.ESTADO_BLOQUEADO, S.ESTADO_PENDIENTE)},
            "incidencias_abiertas": sum(1 for i in incs if i.get("estado")
                                        and i["estado"] != S.INCIDENCIA_CERRADA),
            "incidencias_total": len(incs),
        }

    def evaluate_closure(self, sid, data=None):
        data = data or self.data()
        t = self.totals(sid, data)
        crit = self.config["cierre"]
        blockers = []
        if t["ejecutadas"] == 0:
            blockers.append("No hay pruebas ejecutadas en la sesión.")
        if crit.get("apto_requiere_cero_fallidas") and t["fallidas"]:
            blockers.append(f"{t['fallidas']} prueba(s) fallida(s).")
        if crit.get("apto_requiere_cero_bloqueadas") and t["bloqueadas"]:
            blockers.append(f"{t['bloqueadas']} prueba(s) bloqueada(s).")
        if crit.get("apto_requiere_cero_pendientes") and (t["pendientes"] or t["sin_estado"]):
            blockers.append(f"{t['pendientes'] + t['sin_estado']} prueba(s) pendiente(s) o sin estado.")
        if crit.get("apto_requiere_cero_incidencias_abiertas") and t["incidencias_abiertas"]:
            blockers.append(f"{t['incidencias_abiertas']} incidencia(s) abierta(s).")
        if crit.get("apto_requiere_revision_fisica_sin_fallos"):
            rev = [r for r in data.revisiones if r["sesion_id"] == sid]
            bad = [r["item"] for r in rev if r.get("resultado") in
                   (S.ESTADO_FALLIDO, S.ESTADO_BLOQUEADO, S.ESTADO_PENDIENTE, "")]
            if not rev:
                blockers.append("La revisión física y eléctrica no está registrada.")
            elif bad:
                blockers.append(f"Revisión física con ítems fallidos, bloqueados o pendientes: {len(bad)}.")
        tests = [x for x in data.pruebas if x["sesion_id"] == sid]
        for comp in crit.get("componentes_criticos", []):
            comp_tests = [x for x in tests if x["componente"] == comp]
            if not any(x.get("estado") == S.ESTADO_APROBADO for x in comp_tests):
                blockers.append(f"Componente crítico sin prueba aprobada: {comp}.")
            elif any(x.get("estado") in (S.ESTADO_FALLIDO, S.ESTADO_BLOQUEADO, S.ESTADO_PENDIENTE)
                     for x in comp_tests):
                blockers.append(f"Componente crítico con pruebas fallidas o pendientes: {comp}.")
        if t["fallidas"]:
            sugerido = S.CONCEPTO_NO_APTO
        elif not blockers:
            sugerido = S.CONCEPTO_APTO
        else:
            sugerido = S.CONCEPTO_PENDIENTE
        return {"totales": t, "bloqueos": blockers, "puede_apto": not blockers, "sugerido": sugerido}

    def default_versions_text(self, session):
        def v(key):
            return session.get(key) or "—"
        return (f"Máquina {v('fabricante')} {v('modelo_maquina')} (Serial {v('serial_maquina')}); "
                f"POS {v('modelo_pos')} (Serial {v('serial_pos')}); Firmware NEW5320 {v('firmware')}; "
                f"MDB {v('mdb_estandar')} / {v('mdb_version')} / {v('mdb_modulo')}; "
                f"Financiera {v('version_financiera')}; Agente Polaris {v('version_polaris')}")

    def pending_by_owner(self, sid, data=None):
        data = data or self.data()
        examples = self.example_sessions(data)
        owners = defaultdict(lambda: {"pruebas": [], "incidencias": []})
        for t in data.pruebas:
            if t["sesion_id"] == sid and t.get("estado") in (
                    S.ESTADO_FALLIDO, S.ESTADO_BLOQUEADO, S.ESTADO_PENDIENTE, ""):
                owners[t.get("responsable") or "Sin responsable"]["pruebas"].append(t["id"])
        for i in data.incidencias:
            if (i["sesion_id"] == sid and i.get("estado") and i["estado"] != S.INCIDENCIA_CERRADA
                    and (not self.exclude_examples or not self._is_example_incident(i, examples))):
                owners[i.get("responsable") or "Sin responsable"]["incidencias"].append(i["id"])
        return dict(owners)

    def default_pending_text(self, sid, data=None):
        parts = []
        for owner, items in self.pending_by_owner(sid, data).items():
            detail = []
            if items["pruebas"]:
                detail.append("pruebas " + ", ".join(items["pruebas"]))
            if items["incidencias"]:
                detail.append("incidencias " + ", ".join(items["incidencias"]))
            parts.append(f"{owner}: {'; '.join(detail)}")
        return " | ".join(parts) if parts else "Sin pendientes"

    def save_cierre(self, sid, form):
        with self.store._lock:
            data = self.data()
            session = self.get_session(sid, data)
            if session is None:
                raise ConflictError(f"La sesión {sid} no existe.")
            if session["estado_registro"] == S.ESTADO_REGISTRO_BORRADOR:
                raise ValidationError({}, "Complete la identificación de la sesión antes de cerrarla.")
            values = V.clean(form, ["fecha_cierre", "versiones_cubiertas", "pendientes_area",
                                    "concepto", "responsable_cierre"])
            errors = {}
            for key in ("fecha_cierre", "concepto", "responsable_cierre"):
                if not values.get(key):
                    errors[key] = "Campo obligatorio."
            try:
                if values.get("fecha_cierre"):
                    datetime.strptime(values["fecha_cierre"], "%Y-%m-%d")
            except ValueError:
                errors["fecha_cierre"] = "Use el formato AAAA-MM-DD."
            if values.get("concepto") and values["concepto"] not in data.catalogos["concepto"]:
                errors["concepto"] = "Seleccione un concepto válido."
            ev = self.evaluate_closure(sid, data)
            if values.get("concepto") == S.CONCEPTO_APTO and not ev["puede_apto"]:
                errors["concepto"] = ("No puede declararse 'Apto para piloto': "
                                      + " ".join(ev["bloqueos"]))
            if (values.get("concepto") == S.CONCEPTO_CONDICIONES
                    and self.config["cierre"].get("condiciones_requiere_pendientes_documentados")
                    and (not values.get("pendientes_area") or values["pendientes_area"] == "Sin pendientes")):
                errors["pendientes_area"] = "Documente las condiciones y pendientes del concepto."
            if errors:
                raise ValidationError(errors)
            self.store.write([("save_cierre", {"sesion_id": sid, "fields": values})],
                             f"Cierre de la sesión {sid}")

    @staticmethod
    def client_label(session):
        """Cliente y comercio en una sola línea (equivale al antiguo campo combinado)."""
        cliente, comercio = session.get("cliente", ""), session.get("comercio", "")
        return f"{cliente} - {comercio}" if cliente and comercio else (cliente or comercio)

    @staticmethod
    def legacy_fields(session):
        """Campos del formulario anterior con datos, como [(encabezado, valor)]."""
        labels = dict(S.ID_COLUMNS)
        return [(labels[k], session[k]) for k in S.ID_LEGACY_FIELDS if session.get(k)]

    def objective_templates(self):
        """Objetivo propuesto para cada tipo de prueba (config.json → sesiones.objetivos_por_tipo)."""
        return dict(self.config.get("sesiones", {}).get("objetivos_por_tipo", {}))

    def email_summary(self, sid, overrides=None):
        """Mismo texto que la fórmula 'Resumen para correo' del libro."""
        data = self.data()
        s = self.get_session(sid, data)
        if s is None:
            return ""
        cierre = next((c for c in data.cierres if c["sesion_id"] == sid), {}) or {}
        cierre = dict(cierre)
        cierre.update({k: v for k, v in (overrides or {}).items() if v})
        t = self.totals(sid, data)
        # Visitas con los campos MDB del formulario anterior conservan la línea original del libro.
        if any(s.get(k) for k in ("mdb_estandar", "mdb_version", "mdb_modulo")):
            software = f"MDB: {s.get('mdb_estandar', '')} / {s.get('mdb_version', '')} / {s.get('mdb_modulo', '')}\n"
        else:
            software = (f"Versión de la máquina: {s.get('version_maquina', '')}  |  "
                        f"Gateway MDB: {s.get('version_gateway', '')}\n")
        serie = (f"Visita {s['numero']} de la integración {s['raiz']}\n" if s.get("es_seguimiento") else "")
        pruebas = ""
        for nombre, resultado, observacion in (("MDB", "mdb_resultado", "mdb_observacion"),
                                               ("DEX", "dex_resultado", "dex_observacion")):
            if s.get(resultado) or s.get(observacion):
                detalle = f" — {s[observacion]}" if s.get(observacion) else ""
                pruebas += f"Prueba {nombre}: {s.get(resultado) or 'Sin resultado'}{detalle}\n"
        return (
            f"Resumen de visita — Sesión {sid}\n"
            f"{serie}"
            f"Fecha de la visita: {s.get('fecha', '')}\n"
            f"Cliente / Comercio: {self.client_label(s)}\n"
            f"Máquina: {s.get('fabricante', '')} {s.get('modelo_maquina', '')} (Serial: {s.get('serial_maquina', '')})\n"
            f"POS: {s.get('modelo_pos', '')} (Serial: {s.get('serial_pos', '')}) — Firmware: {s.get('firmware', '')}\n"
            f"{software}"
            f"Financiera: {s.get('version_financiera', '')}  |  Agente Polaris: {s.get('version_polaris', '')}\n"
            f"Participantes: {s.get('participantes', '')} (Responsable: {s.get('responsable', '')})\n"
            f"Objetivo: {s.get('objetivo', '')}\n\n"
            f"{pruebas + chr(10) if pruebas else ''}"
            f"Resultado de pruebas: {t['ejecutadas']}/{t['planificadas']} ejecutadas — "
            f"Aprobadas: {t['aprobadas']}, Fallidas: {t['fallidas']}, Bloqueadas: {t['bloqueadas']}, "
            f"Pendientes: {t['pendientes']}\n"
            f"Incidencias abiertas: {t['incidencias_abiertas']}\n\n"
            f"Concepto final: {cierre.get('concepto', '')}\n"
            f"Pendientes: {cierre.get('pendientes_area', '')}"
        )

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def filter_sessions(self, sessions, f):
        def contains(value, needle):
            return needle.casefold() in (value or "").casefold()

        out = []
        q = (f.get("q") or "").strip()
        for s in sessions:
            if q and not any(contains(s.get(k), q) for k in (
                    "sesion_id", "cliente", "comercio", "fabricante", "modelo_maquina", "serial_maquina",
                    "modelo_pos", "serial_pos", "firmware", "responsable", "ciudad", "pais")):
                continue
            if f.get("cliente") and not contains(s.get("cliente"), f["cliente"]):
                continue
            if any(f.get(key) and s.get(key) != f[key] for key in
                   ("pais", "fabricante", "modelo_maquina", "firmware", "estado_registro")):
                continue
            if f.get("categoria") and s["categoria"] != f["categoria"]:
                continue
            if f.get("desde") and (s.get("fecha") or "") < f["desde"]:
                continue
            if f.get("hasta") and (s.get("fecha") or "9999") > f["hasta"]:
                continue
            out.append(s)
        return out

    def dashboard(self, f):
        data = self.data()
        sessions = self.filter_sessions(self.sessions(data), f)
        sids = {s["sesion_id"] for s in sessions}
        examples = self.example_sessions(data)
        tests = [t for t in data.pruebas if t["sesion_id"] in sids]
        incs = [i for i in data.incidencias if i["sesion_id"] in sids
                and (not self.exclude_examples or not self._is_example_incident(i, examples))]
        estados = Counter(t.get("estado") or "Sin estado" for t in tests)
        categorias = Counter(s["categoria"] for s in sessions)
        modelos = {(s.get("fabricante"), s.get("modelo_maquina")) for s in sessions
                   if s.get("fabricante") or s.get("modelo_maquina")}
        paises = Counter(s["pais"] for s in sessions if s.get("pais"))
        recent = sorted(sessions, key=lambda s: (s.get("fecha", ""), s.get("hora", ""), s["sesion_id"]),
                        reverse=True)[:6]
        return {
            "total_sesiones": len(sessions),
            "modelos": len(modelos),
            "categorias": {k: categorias.get(k, 0) for k in INTEGRATION_CATEGORIES},
            "pruebas_total": len(tests),
            "pruebas": {e: estados.get(e, 0) for e in (S.ESTADO_APROBADO, S.ESTADO_FALLIDO,
                                                       S.ESTADO_BLOQUEADO, S.ESTADO_PENDIENTE)},
            "pruebas_otros": sum(n for e, n in estados.items() if e not in (
                S.ESTADO_APROBADO, S.ESTADO_FALLIDO, S.ESTADO_BLOQUEADO, S.ESTADO_PENDIENTE)),
            "inc_abiertas": sum(1 for i in incs if i.get("estado") and i["estado"] != S.INCIDENCIA_CERRADA),
            "inc_cerradas": sum(1 for i in incs if i.get("estado") == S.INCIDENCIA_CERRADA),
            "paises": paises.most_common(),
            "sin_pais": sum(1 for s in sessions if not s.get("pais")),
            "recientes": recent,
            "excluidas_ejemplo": len(examples) if self.exclude_examples else 0,
        }

    def filter_options(self, sessions):
        def uniq(key):
            return sorted({s.get(key) for s in sessions if s.get(key)}, key=str.casefold)
        return {k: uniq(k) for k in ("pais", "fabricante", "modelo_maquina", "firmware", "cliente")}

    def machines(self):
        groups = OrderedDict()
        for s in sorted(self.sessions(), key=lambda x: x.get("fecha", "")):
            key = (s.get("fabricante") or "Sin fabricante", s.get("modelo_maquina") or "Sin modelo")
            g = groups.setdefault(key, {"fabricante": key[0], "modelo": key[1], "sesiones": [],
                                        "seriales": set(), "firmwares": set()})
            g["sesiones"].append(s)
            if s.get("serial_maquina"):
                g["seriales"].add(s["serial_maquina"])
            if s.get("firmware"):
                g["firmwares"].add(s["firmware"])
        result = []
        for g in groups.values():
            last = g["sesiones"][-1]
            result.append({**g, "ultima": last, "seriales": sorted(g["seriales"]),
                           "firmwares": sorted(g["firmwares"])})
        return sorted(result, key=lambda g: g["ultima"].get("fecha", ""), reverse=True)

    def all_tests(self, f):
        data = self.data()
        visible = {s["sesion_id"]: s for s in self.sessions(data)}
        out = []
        for t in data.pruebas:
            s = visible.get(t["sesion_id"])
            if s is None:
                continue
            if f.get("componente") and t["componente"] != f["componente"]:
                continue
            if f.get("estado") and (t.get("estado") or "") != f["estado"]:
                continue
            if f.get("responsable") and t.get("responsable") != f["responsable"]:
                continue
            if f.get("sesion") and t["sesion_id"] != f["sesion"]:
                continue
            if f.get("serial_pos") and s.get("serial_pos") != f["serial_pos"]:
                continue
            q = (f.get("q") or "").casefold()
            if q and not any(q in (t.get(k) or "").casefold() for k in
                             ("id", "objetivo", "observaciones", "resultado_obtenido")):
                continue
            out.append(dict(t, sesion=s, plantilla=_has_marker(t)))
        return out

    def all_incidents(self, f):
        data = self.data()
        visible = {s["sesion_id"]: s for s in self.sessions(data)}
        examples = self.example_sessions(data)
        out = []
        for i in data.incidencias:
            s = visible.get(i["sesion_id"])
            ejemplo = self._is_example_incident(i, examples)
            if s is None or (ejemplo and self.exclude_examples and not f.get("ver_ejemplos")):
                continue
            if f.get("estado") and i.get("estado") != f["estado"]:
                continue
            if f.get("severidad") and i.get("severidad") != f["severidad"]:
                continue
            if f.get("sesion") and i["sesion_id"] != f["sesion"]:
                continue
            if f.get("responsable") and i.get("responsable") != f["responsable"]:
                continue
            out.append(dict(i, sesion=s, es_ejemplo=ejemplo))
        return out

    def compare(self, sids):
        data = self.data()
        rows = []
        for sid in sids:
            s = self.get_session(sid, data)
            if s:
                rows.append({"sesion": s, "totales": self.totals(sid, data)})
        components = sorted({t["componente"] for t in data.pruebas if t["sesion_id"] in sids})
        matrix = {}
        for t in data.pruebas:
            if t["sesion_id"] in sids:
                matrix.setdefault(t["componente"], {}).setdefault(t["sesion_id"], []).append(t)
        return {"filas": rows, "componentes": components, "matriz": matrix}

    def history(self, tipo=None, registro_id=None):
        data = self.data()
        return [h for h in data.historial
                if (not tipo or h["tipo_registro"] == tipo)
                and (not registro_id or h["registro_id"] == registro_id)]
