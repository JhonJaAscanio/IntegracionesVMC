"""Lógica de negocio: sesiones, revisiones, pruebas, incidencias y cierre."""
import json
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime

from . import schema as S
from . import validators as V
from .excel_store import ConflictError
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
    def __init__(self, store, config):
        self.store = store
        self.config = config

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
        }

    # ------------------------------------------------------------------
    # Identificadores
    # ------------------------------------------------------------------
    def next_id(self, prefix, data=None):
        data = data or self.data()
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        numbers = [0]
        for rows, key in ((data.sesiones, "sesion_id"), (data.pruebas, "id"),
                          (data.incidencias, "id"), (data.evidencias, "id")):
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

    def create_session(self, form, draft=False):
        with self.store._lock:
            data = self.data()
            values = V.clean(form, V.SESSION_FIELDS)
            V.validate_session(values, data.catalogos, draft)
            sid = self.next_id("SES", data)
            if any(s["sesion_id"] == sid for s in data.sesiones):
                raise ConflictError("No se pudo generar un Sesión ID único.")
            values["sesion_id"] = sid
            estado = S.ESTADO_REGISTRO_BORRADOR if draft else S.ESTADO_REGISTRO_EN_CURSO
            ops = self._ensure_catalog_ops(data, "fabricante", values.get("fabricante"))
            ops.append(("create_session", {"sesion": values, "estado_registro": estado}))
            self.store.write(ops, f"Nueva sesión {sid}")
            return sid

    def update_session(self, sid, form, draft=False):
        with self.store._lock:
            data = self.data()
            session = self.get_session(sid, data)
            if session is None:
                raise ConflictError(f"La sesión {sid} no existe.")
            values = V.clean(form, V.SESSION_FIELDS)
            V.validate_session(values, data.catalogos, draft)
            estado = None
            if session["estado_registro"] == S.ESTADO_REGISTRO_BORRADOR and not draft:
                estado = S.ESTADO_REGISTRO_EN_CURSO
            ops = self._ensure_catalog_ops(data, "fabricante", values.get("fabricante"))
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
        return (
            f"Resumen de visita — Sesión {sid}\n"
            f"Fecha de la visita: {s.get('fecha', '')}\n"
            f"Cliente / Comercio: {s.get('cliente', '')}\n"
            f"Máquina: {s.get('fabricante', '')} {s.get('modelo_maquina', '')} (Serial: {s.get('serial_maquina', '')})\n"
            f"POS: {s.get('modelo_pos', '')} (Serial: {s.get('serial_pos', '')}) — Firmware: {s.get('firmware', '')}\n"
            f"MDB: {s.get('mdb_estandar', '')} / {s.get('mdb_version', '')} / {s.get('mdb_modulo', '')}\n"
            f"Financiera: {s.get('version_financiera', '')}  |  Agente Polaris: {s.get('version_polaris', '')}\n"
            f"Participantes: {s.get('participantes', '')} (Responsable: {s.get('responsable', '')})\n"
            f"Objetivo: {s.get('objetivo', '')}\n\n"
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
                    "sesion_id", "cliente", "fabricante", "modelo_maquina", "serial_maquina",
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
