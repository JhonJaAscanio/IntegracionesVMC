"""Casos puntuales fallidos: se registran en la visita y se heredan como pendientes en el seguimiento."""
from conftest import SESSION_FORM, service
from wposs_vim import schema as S

CASOS = {"caso-1-texto": "Venta sin contacto en bandeja 12", "caso-1-obs": "El VMC no confirma la entrega",
         "caso-2-texto": "Lectura DEX remota", "caso-2-obs": "Tiempo de espera agotado"}


def _casos(svc, sid):
    return [r for r in svc.data().checklist_res
            if r["sesion_id"] == sid and r["seccion"] == S.SECCION_CASOS_PUNTUALES]


def test_crear_visita_con_casos_puntuales(client, app):
    r = client.post("/visitas/nueva", {**SESSION_FORM, "accion": "guardar", **CASOS})
    assert r.status_code == 302
    sid = r.headers["Location"].rsplit("/", 1)[-1]
    svc = service(app)
    casos = _casos(svc, sid)
    assert [c["texto"] for c in casos] == ["Venta sin contacto en bandeja 12", "Lectura DEX remota"]
    assert {c["resultado"] for c in casos} == {S.RESULTADO_FALLIDA}
    assert [c["item_id"] for c in casos] == ["CAS-001", "CAS-002"]
    assert casos[0]["observacion"] == "El VMC no confirma la entrega"
    assert svc.data().contadores.get("CAS") == "2"
    page = client.get(f"/visitas/{sid}?tab=checklist").get_data(as_text=True)
    assert S.SECCION_CASOS_PUNTUALES in page and "Lectura DEX remota" in page


def test_caso_incompleto_rechazado_sin_crear_visita(client, app):
    before = len(service(app).data().sesiones)
    r = client.post("/visitas/nueva", {**SESSION_FORM, "accion": "guardar", "caso-1-texto": "Venta en efectivo"})
    assert r.status_code == 422 and "Describa qué falló en este caso." in r.get_data(as_text=True)
    assert len(service(app).data().sesiones) == before


def test_seguimiento_hereda_y_resuelve_casos(client, app):
    svc = service(app)
    sid = svc.create_session({**SESSION_FORM, **CASOS})
    form = svc.followup_defaults(sid)
    page = client.get(f"/visitas/nueva?origen={sid}").get_data(as_text=True)
    assert "Venta sin contacto en bandeja 12" in page and "El VMC no confirma la entrega" in page
    r = client.post("/visitas/nueva", {**form, "accion": "guardar",
                                       "chk-CAS-001-resultado": "Exitosa",
                                       "chk-CAS-001-obs": "Resuelto con firmware nuevo"})
    assert r.status_code == 302
    pendientes = {p["item_id"] for p in svc.series_pending(sid)}
    assert "CAS-001" not in pendientes and "CAS-002" in pendientes


def test_agregar_casos_desde_la_ficha_y_al_editar(client, app):
    svc = service(app)
    sid = svc.create_session(SESSION_FORM)
    r = client.post(f"/visitas/{sid}/checklist/casos", {"caso-1-texto": "Cambio de monedas",
                                                         "caso-1-obs": "Monedero no responde"})
    assert r.status_code == 302
    r = client.post(f"/visitas/{sid}/checklist/casos", {})
    assert r.status_code == 422
    svc.update_session(sid, {**SESSION_FORM, "caso-1-texto": "Reinicio del POS", "caso-1-obs": "Se congela"})
    casos = _casos(svc, sid)
    assert [(c["texto"], c["orden"]) for c in casos] == [("Cambio de monedas", "1"), ("Reinicio del POS", "2")]
    assert svc.create_session(SESSION_FORM) == "SES-" + f"{int(sid.split('-')[1]) + 1:03d}"
    historial = [h for h in svc.data().historial if h.get("registro_id") == casos[0]["item_id"]]
    assert historial and historial[0]["accion"] == "Caso puntual registrado"
