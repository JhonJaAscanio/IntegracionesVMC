"""Checklist de integración: plantilla por tipo de prueba, resultados por visita y gestión."""
import pytest

from conftest import SESSION_FORM, Client, service
from wposs_vim import schema as S
from wposs_vim.excel_store import open_workbook
from wposs_vim.validators import ValidationError


def _items(app, tipo="Nueva Integración", **kw):
    return service(app).checklist_items(tipo, **kw)


def test_plantilla_inicial_nueva_integracion(app):
    items = _items(app)
    assert len(items) == 13
    secciones = service(app).group_sections(items)
    assert [s for s, _ in secciones] == ["Preguntas iniciales", "Prueba terminal 5320"]
    assert [len(i) for _, i in secciones] == [8, 5]
    assert items[0]["texto"].startswith("Verificar los implementos necesarios para la visita")
    assert items[-1]["texto"].startswith("Revisar que el precio del producto coincida")
    assert _items(app, "Reintegración") == []
    wb = open_workbook(app.extensions["wposs"]["paths"].trabajo)
    assert S.SHEET_APP_CHECKLIST in wb.sheetnames and S.SHEET_APP_CHECKLIST_RES in wb.sheetnames


def test_nueva_visita_guarda_resultados_del_checklist(client, app):
    items = _items(app)
    form = {**SESSION_FORM, "accion": "guardar",
            f"chk-{items[0]['id']}-resultado": "Exitosa",
            f"chk-{items[1]['id']}-resultado": "Fallida", f"chk-{items[1]['id']}-obs": "Firmware 13.0.15",
            f"chk-{items[2]['id']}-resultado": "No aplica"}
    r = client.post("/visitas/nueva", form)
    assert r.status_code == 302
    sid = r.headers["Location"].rsplit("/", 1)[-1]
    chk = service(app).session_checklist(sid)
    assert chk["total"] == 13 and chk["exitosas"] == 1 and chk["fallidas"] == 1 and chk["sin_marcar"] == 10
    fila = chk["secciones"][0][1][1]
    assert fila["resultado"] == "Fallida" and fila["observacion"] == "Firmware 13.0.15"
    page = client.get(f"/visitas/{sid}?tab=checklist").get_data(as_text=True)
    assert "Firmware 13.0.15" in page and "Guardar checklist" in page


def test_paso_fallido_sin_observacion_no_guarda_y_conserva_datos(client, app):
    items = _items(app)
    before = len(service(app).data().sesiones)
    r = client.post("/visitas/nueva", {**SESSION_FORM, "accion": "guardar", "responsable": "",
                                       f"chk-{items[3]['id']}-resultado": "Fallida",
                                       f"chk-{items[4]['id']}-resultado": "Exitosa"})
    assert r.status_code == 422
    html = r.get_data(as_text=True)
    assert "Describa qué falló en este paso." in html and "Campo obligatorio." in html
    assert f'name="chk-{items[4]["id"]}-resultado" value="Exitosa" checked' in html
    assert len(service(app).data().sesiones) == before


def test_actualizar_checklist_desde_la_ficha_con_historial(client, app):
    sid = service(app).create_session(SESSION_FORM)
    chk = service(app).session_checklist(sid)
    primero = chk["secciones"][0][1][0]["item_id"]
    r = client.post(f"/visitas/{sid}/checklist", {f"chk-{primero}-resultado": "Exitosa",
                                                   f"chk-{primero}-obs": "Implementos completos"})
    assert r.status_code == 302
    fila = service(app).session_checklist(sid)["secciones"][0][1][0]
    assert fila["resultado"] == "Exitosa" and fila["observacion"] == "Implementos completos"
    assert any(h["registro_id"] == primero and h["accion"] == "Resultado actualizado"
               for h in service(app).data().historial)
    r = client.post(f"/visitas/{sid}/checklist", {f"chk-{primero}-resultado": "Fallida"})
    assert r.status_code == 422 and "Describa qué falló" in r.get_data(as_text=True)


def test_visita_existente_sin_checklist_puede_cargarlo(client, app):
    svc = service(app)
    s = svc.get_session("SES-002")
    svc.update_session("SES-002", {**{k: s.get(k, "") for k in ("fecha", "responsable", "cliente", "objetivo",
                                                                 "fabricante", "modelo_maquina", "modelo_pos",
                                                                 "firmware")}, "tipo_prueba": "Nueva Integración"})
    assert svc.session_checklist("SES-002")["total"] == 0
    assert "Cargar checklist" in client.get("/visitas/SES-002?tab=checklist").get_data(as_text=True)
    client.post("/visitas/SES-002/checklist/cargar")
    assert svc.session_checklist("SES-002")["total"] == 13


def test_gestion_agregar_editar_mover_quitar(client, app):
    svc = service(app)
    assert "Checklists de integración" in client.get("/checklists").get_data(as_text=True)
    client.post("/checklists/item", {"tipo": "Nueva Integración", "seccion": "Prueba terminal 5320",
                                     "texto": "Validar la lectura del archivo DEX."})
    client.post("/checklists/item", {"tipo": "Reintegración", "seccion_nueva": "Revisión de configuración",
                                     "texto": "Comparar la configuración MDB con la integración anterior."})
    items = _items(app)
    nuevo = items[-1]
    assert len(items) == 14 and nuevo["texto"] == "Validar la lectura del archivo DEX." and nuevo["orden"] == "6"
    assert _items(app, "Reintegración")[0]["seccion"] == "Revisión de configuración"
    # Editar texto.
    client.post(f"/checklists/item/{nuevo['id']}", {"tipo_actual": "Nueva Integración",
                                                    "seccion": "Prueba terminal 5320",
                                                    "texto": "Validar la lectura y el envío del archivo DEX."})
    assert _items(app)[-1]["texto"] == "Validar la lectura y el envío del archivo DEX."
    # Subir una posición.
    client.post(f"/checklists/item/{nuevo['id']}/mover", {"tipo_actual": "Nueva Integración", "direccion": "subir"})
    seccion = dict(svc.group_sections(_items(app)))["Prueba terminal 5320"]
    assert seccion[-2]["id"] == nuevo["id"]
    # Quitar: no se muestra en visitas nuevas, se conserva y se puede restaurar.
    client.post(f"/checklists/item/{nuevo['id']}/estado", {"tipo_actual": "Nueva Integración", "activo": "no"})
    assert all(i["id"] != nuevo["id"] for i in _items(app))
    assert any(i["id"] == nuevo["id"] for i in _items(app, include_inactive=True))
    client.post(f"/checklists/item/{nuevo['id']}/estado", {"tipo_actual": "Nueva Integración", "activo": "si"})
    assert any(i["id"] == nuevo["id"] for i in _items(app))


def test_cambios_de_plantilla_no_alteran_visitas_registradas(app):
    svc = service(app)
    sid = svc.create_session(SESSION_FORM)
    item = _items(app)[0]
    svc.update_checklist_item(item["id"], {"seccion": item["seccion"], "texto": "Texto cambiado"})
    svc.set_checklist_item_active(_items(app)[1]["id"], False)
    fila = svc.session_checklist(sid)["secciones"][0][1][0]
    assert fila["texto"].startswith("Verificar los implementos necesarios")
    assert svc.session_checklist(sid)["total"] == 13


def test_validacion_de_items(app):
    with pytest.raises(ValidationError):
        service(app).add_checklist_item({"tipo": "Nueva Integración", "seccion": "", "texto": ""})
    with pytest.raises(ValidationError):
        service(app).add_checklist_item({"tipo": "Inventado", "seccion": "X", "texto": "Y"})


def test_checklist_en_informe(client, app):
    items = _items(app)
    r = client.post("/visitas/nueva", {**SESSION_FORM, "accion": "guardar",
                                       f"chk-{items[0]['id']}-resultado": "Exitosa"})
    sid = r.headers["Location"].rsplit("/", 1)[-1]
    client.post(f"/carpetas/{sid}/informe")
    informe = next(e for e in service(app).data().evidencias if e.get("categoria") == "Informe generado")
    html = client.get(f"/archivo/{informe['ruta']}").get_data(as_text=True)
    assert "Checklist de la integración — Nueva Integración" in html
    assert "1 exitosos · 0 fallidos · 12 sin marcar · 13 pasos" in html
