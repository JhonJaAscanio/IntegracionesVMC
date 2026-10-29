"""Visitas de seguimiento: varias visitas a una misma máquina dentro de una integración."""
from conftest import SESSION_FORM, Client, prueba_data, service
from wposs_vim import schema as S


def _origen_con_checklist(client, app):
    """Visita de origen con el paso 1 exitoso, el 2 fallido y el resto sin marcar."""
    items = service(app).checklist_items("Nueva Integración")
    r = client.post("/visitas/nueva", {**SESSION_FORM, "accion": "guardar",
                                       f"chk-{items[0]['id']}-resultado": "Exitosa",
                                       f"chk-{items[1]['id']}-resultado": "Fallida",
                                       f"chk-{items[1]['id']}-obs": "Firmware desactualizado"})
    return r.headers["Location"].rsplit("/", 1)[-1], items


def test_formulario_de_seguimiento_precargado(client, app):
    sid, _ = _origen_con_checklist(client, app)
    service(app).update_session(sid, {**SESSION_FORM, "firmware": "13.0.17", "version_gateway": "GW 2.0"})
    page = client.get(f"/visitas/nueva?origen={sid}").get_data(as_text=True)
    assert "Visita de seguimiento" in page and f"Visita 2 de la integración <span class=\"mono\">{sid}</span>" in page
    assert f'name="sesion_origen" value="{sid}"' in page
    assert 'value="GW 2.0"' in page and '<option value="13.0.17" selected>' in page
    assert '<option value="Integración de seguimiento" selected>' in page
    assert "Pendientes de visitas anteriores" in page and "Antes: Fallida" in page
    assert client.get("/visitas/nueva?origen=SES-999").status_code == 404


def test_crear_seguimiento_vincula_y_hereda_pendientes(client, app):
    sid, items = _origen_con_checklist(client, app)
    form = {**service(app).followup_defaults(sid), "accion": "guardar",
            f"chk-{items[1]['id']}-resultado": "Exitosa"}
    r = client.post("/visitas/nueva", form)
    assert r.status_code == 302
    sid2 = r.headers["Location"].rsplit("/", 1)[-1]
    s2 = service(app).get_session(sid2)
    assert s2["sesion_origen"] == sid and s2["numero"] == 2 and s2["es_seguimiento"]
    chk = service(app).session_checklist(sid2)
    assert chk["total"] == 12  # 13 pasos menos el que ya fue exitoso en la visita 1
    assert [sec for sec, _ in chk["secciones"]] == [S.SECCION_PENDIENTES]
    # El paso que falló en la visita 1 y fue exitoso en la 2 ya no queda pendiente.
    pendientes = {r["item_id"] for r in service(app).series_pending(sid)}
    assert items[1]["id"] not in pendientes and items[0]["id"] not in pendientes
    assert len(pendientes) == 11


def test_seguimiento_de_seguimiento_apunta_al_origen(app):
    svc = service(app)
    sid = svc.create_session(SESSION_FORM)
    sid2 = svc.create_session({**svc.followup_defaults(sid), "incluir_pendientes": "no"})
    sid3 = svc.create_session(svc.followup_defaults(sid2))
    s3 = svc.get_session(sid3)
    assert s3["sesion_origen"] == sid and s3["numero"] == 3
    assert [v["sesion_id"] for v in svc.series(sid)] == [sid, sid2, sid3]
    assert svc.session_checklist(sid2)["total"] == 0  # pendientes excluidos y el tipo no tiene plantilla


def test_editar_no_rompe_el_vinculo(client, app):
    svc = service(app)
    sid = svc.create_session(SESSION_FORM)
    sid2 = svc.create_session(svc.followup_defaults(sid))
    r = client.post(f"/visitas/{sid2}/editar", {**SESSION_FORM, "accion": "guardar", "sesion_origen": "",
                                                "numero_visita": "9"})
    assert r.status_code == 302
    s2 = svc.get_session(sid2)
    assert s2["sesion_origen"] == sid and s2["numero"] == 2


def test_ficha_muestra_linea_de_tiempo_y_pendientes(client, app):
    svc = service(app)
    sid = svc.create_session(SESSION_FORM)
    svc.create_test(prueba_data(sid, estado="Fallido", resultado_obtenido="Sin respuesta"))
    sid2 = svc.create_session(svc.followup_defaults(sid))
    page = client.get(f"/visitas/{sid2}").get_data(as_text=True)
    assert "Visitas de esta integración" in page and "Visita 2 de 2" in page
    assert sid in page and "Esta visita" in page
    assert "1 prueba(s)" in page  # la prueba fallida de la visita 1
    assert "Visita de seguimiento" in page
    lista = client.get("/visitas").get_data(as_text=True)
    assert f"Visita 2 · {sid}" in lista


def test_resumen_e_informe_indican_la_serie(client, app):
    svc = service(app)
    sid = svc.create_session(SESSION_FORM)
    sid2 = svc.create_session(svc.followup_defaults(sid))
    assert f"Visita 2 de la integración {sid}" in svc.email_summary(sid2)
    assert "Visita 2 de la integración" not in svc.email_summary(sid)
    datos = client.get(f"/carpetas/{sid2}?vista=expediente").get_data(as_text=True)
    assert "Visitas de la integración" in datos and f"origen {sid}" in datos


def test_origen_inexistente_rechazado(client, app):
    before = len(service(app).data().sesiones)
    r = client.post("/visitas/nueva", {**SESSION_FORM, "accion": "guardar", "sesion_origen": "SES-999"})
    assert r.status_code == 422 and "La visita de origen no existe." in r.get_data(as_text=True)
    assert len(service(app).data().sesiones) == before
