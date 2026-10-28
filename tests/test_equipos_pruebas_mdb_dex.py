"""Código del fabricante, nivel, versiones de software y pruebas MDB/DEX de la visita."""
import io

import pytest

from conftest import SESSION_FORM, Client, service
from wposs_vim import schema as S
from wposs_vim.excel_store import open_workbook
from wposs_vim.validators import ValidationError

NUEVOS = {
    "codigo_fabricante": "FAB-7781", "nivel_maquina": "Nivel 3", "version_maquina": "VMC 4.2.1",
    "version_gateway": "MDB_GATEWAY_1.0.5", "mdb_resultado": "Exitosa",
    "mdb_observacion": "Sesión de venta y aprobación correctas", "dex_resultado": "Fallida",
    "dex_archivo": "No", "dex_customer_id": "CUST-01", "dex_provider_id": "PROV-02",
    "dex_observacion": "Sin respuesta del puerto DEX",
}


def test_campos_nuevos_se_guardan_en_columnas_al_final(app):
    sid = service(app).create_session({**SESSION_FORM, **NUEVOS})
    s = service(app).get_session(sid)
    for key, value in NUEVOS.items():
        assert s[key] == value
    wb = open_workbook(app.extensions["wposs"]["paths"].trabajo)
    headers = [c.value for c in wb[S.SHEET_ID][1]]
    assert headers[:26][-1] == "Observaciones"  # columnas originales sin mover
    for _, header in S.ID_COLUMNS[-11:]:
        assert header in headers[26:]
    assert service(app).data().catalogos["nivel_maquina"] == ["Nivel 1", "Nivel 2", "Nivel 3"]
    assert service(app).data().catalogos["resultado_prueba"] == ["Exitosa", "Fallida", "No realizada", "No aplica"]


@pytest.mark.parametrize("resultado,observacion", [("mdb_resultado", "mdb_observacion"),
                                                   ("dex_resultado", "dex_observacion")])
def test_prueba_fallida_exige_describir_el_error(app, resultado, observacion):
    with pytest.raises(ValidationError) as exc:
        service(app).create_session({**SESSION_FORM, resultado: "Fallida", observacion: ""})
    assert observacion in exc.value.errors


def test_valores_invalidos_rechazados(app):
    with pytest.raises(ValidationError) as exc:
        service(app).create_session({**SESSION_FORM, "nivel_maquina": "Nivel 9", "mdb_resultado": "Regular",
                                     "dex_archivo": "Tal vez"})
    assert {"nivel_maquina", "mdb_resultado", "dex_archivo"} <= set(exc.value.errors)


def test_editar_conserva_campos_del_formulario_anterior(client, app):
    sid = service(app).create_session(SESSION_FORM)  # incluye MDB estándar/versión/módulo
    form = {k: v for k, v in SESSION_FORM.items() if k not in S.ID_LEGACY_FIELDS}
    r = client.post(f"/visitas/{sid}/editar", {**form, **NUEVOS, "accion": "guardar"})
    assert r.status_code == 302
    s = service(app).get_session(sid)
    assert s["mdb_estandar"] == "MDB 4.2" and s["mdb_modulo"] == "mdb_mod"
    assert s["version_gateway"] == "MDB_GATEWAY_1.0.5"


def test_formulario_y_vistas_muestran_las_nuevas_secciones(client, app):
    page = client.get("/visitas/nueva").get_data(as_text=True)
    for texto in ("Código del fabricante", "Nivel de la máquina", "Versión de la máquina",
                  "Versión del gateway MDB", "Pruebas MDB y DEX", "Prueba MDB", "Prueba DEX",
                  "Archivo DEX obtenido", "Customer ID DEX", "Provider ID DEX", "Archivos DEX"):
        assert texto in page
    assert "Instalación y notas" not in page and "MDB — Estándar / Especificación" not in page
    sid = service(app).create_session({**SESSION_FORM, **NUEVOS})
    ficha = client.get(f"/visitas/{sid}").get_data(as_text=True)
    assert "FAB-7781" in ficha and "Sin respuesta del puerto DEX" in ficha
    datos = client.get(f"/carpetas/{sid}?vista=expediente").get_data(as_text=True)
    assert "MDB_GATEWAY_1.0.5" in datos and "Datos registrados con el formulario anterior" in datos


def test_resumen_incluye_software_y_pruebas(app):
    form = {k: v for k, v in SESSION_FORM.items() if k not in S.ID_LEGACY_FIELDS}
    sid = service(app).create_session({**form, **NUEVOS})
    text = service(app).email_summary(sid)
    assert "Versión de la máquina: VMC 4.2.1  |  Gateway MDB: MDB_GATEWAY_1.0.5" in text
    assert "Prueba MDB: Exitosa — Sesión de venta y aprobación correctas" in text
    assert "Prueba DEX: Fallida — Sin respuesta del puerto DEX" in text
    assert "\nMDB: " not in text


def test_archivo_dex_en_subcarpeta(app):
    c = Client(app)
    sid = service(app).create_session(SESSION_FORM)
    c.post(f"/visitas/{sid}/evidencias", {"tipo_registro": "Visita", "categoria": "Archivo DEX",
                                         "archivo": (io.BytesIO(b"DXS*9252131001*VA*V0/6*1"), "auditoria.dex")},
           content_type="multipart/form-data")
    ev = next(e for e in service(app).data().evidencias if e["sesion_id"] == sid)
    assert ev["ruta"] == f"evidencias/{sid}/logs/dex/auditoria.dex"
    assert c.get(f"/carpetas/{sid}/ver?ruta={ev['ruta']}").status_code == 200
    assert "auditoria.dex" in c.get(f"/carpetas/{sid}?sub=logs/dex").get_data(as_text=True)
