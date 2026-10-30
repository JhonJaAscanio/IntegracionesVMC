"""Catálogos definidos por WPOSS: clientes, países, ciudades, firmware, tipos de prueba y objetivos."""
import html as html_lib

import pytest

from conftest import SESSION_FORM, Client, make_app, service
from wposs_vim import schema as S
from wposs_vim.excel_store import catalog_column, open_workbook
from wposs_vim.validators import ValidationError


def test_catalogos_sembrados(app):
    data = service(app).data()
    assert data.catalogos["pais"] == ["Ecuador", "Costa Rica", "Bolivia"]
    assert data.catalogos["cliente"] == ["DATAFAST", "MEDIANET", "ATC", "PROMERICA CR"]
    assert data.clientes_pais == {"DATAFAST": "Ecuador", "MEDIANET": "Ecuador", "ATC": "Bolivia",
                                  "PROMERICA CR": "Costa Rica"}
    assert data.catalogos["firmware"] == ["13.0.11", "13.0.13", "13.0.14", "13.0.15", "13.0.17", "13.0.22"]
    assert set(data.ciudades) == {"Ecuador", "Costa Rica", "Bolivia"}
    assert "Quito" in data.ciudades["Ecuador"] and "San José" in data.ciudades["Costa Rica"]
    assert "La Paz" in data.ciudades["Bolivia"]
    assert data.catalogos["tipo_prueba"] == S.TIPOS_PRUEBA


def test_tipos_de_prueba_reemplazados_con_historial(app):
    data = service(app).data()
    hist = [h for h in data.historial if h["registro_id"] == "Tipo de prueba (sesión)"]
    assert hist and hist[0]["anterior"].startswith("Instalación; Diagnóstico")
    # Los registros existentes conservan su tipo de prueba anterior.
    assert service(app).get_session("SES-002")["tipo_prueba"] == "Compatibilidad"


def test_paises_anteriores_reemplazados_solo_si_no_cambiaron(workdir):
    app = make_app(workdir)
    paths = app.extensions["wposs"]["paths"]
    store = app.extensions["wposs"]["store"]

    def set_paises(values):
        wb = open_workbook(paths.trabajo)
        ws = wb[S.SHEET_LISTAS]
        col = catalog_column(wb, "pais")
        for r in range(2, ws.max_row + 1):
            ws.cell(r, col).value = None
        for i, v in enumerate(values, start=2):
            ws.cell(i, col).value = v
        store._save_atomic(wb)

    set_paises(S.LEGACY_SEED_PAISES)
    app = make_app(workdir)
    assert service(app).data().catalogos["pais"] == S.SEED_PAISES
    # Si el usuario ya personalizó la lista, no se toca.
    set_paises(["Ecuador", "Bolivia", "Perú"])
    app = make_app(workdir)
    assert service(app).data().catalogos["pais"] == ["Ecuador", "Bolivia", "Perú"]


@pytest.mark.parametrize("campo,valor,clave", [
    ("cliente", "OTRO BANCO", "cliente"),
    ("firmware", "13.0.30", "firmware"),
    ("tipo_prueba", "Compatibilidad", "tipo_prueba"),
    ("pais", "Colombia", "pais"),
])
def test_valores_fuera_de_catalogo_rechazados(app, campo, valor, clave):
    with pytest.raises(ValidationError) as exc:
        service(app).create_session({**SESSION_FORM, campo: valor})
    assert clave in exc.value.errors


def test_ciudad_requiere_pais(app):
    with pytest.raises(ValidationError) as exc:
        service(app).create_session({**SESSION_FORM, "pais": "", "ciudad": "Quito"})
    assert "ciudad" in exc.value.errors
    sid = service(app).create_session({**SESSION_FORM, "cliente": "ATC", "pais": "Bolivia",
                                       "ciudad": "santa cruz de la sierra"})
    assert service(app).get_session(sid)["ciudad"] == "Santa Cruz de la Sierra"  # unificada con el catálogo


def test_ciudad_nueva_se_agrega_al_catalogo_del_pais(client, app):
    svc = service(app)
    antes = svc.data().ciudades
    assert "Uyuni" not in antes.get("Bolivia", [])
    sid = svc.create_session({**SESSION_FORM, "cliente": "ATC", "pais": "Bolivia", "ciudad": "Uyuni"})
    assert svc.get_session(sid)["ciudad"] == "Uyuni"
    ciudades = svc.data().ciudades
    assert ciudades["Bolivia"].count("Uyuni") == 1
    assert all("Uyuni" not in v for k, v in ciudades.items() if k != "Bolivia")
    svc.create_session({**SESSION_FORM, "cliente": "ATC", "pais": "Bolivia", "ciudad": "UYUNI"})
    assert svc.data().ciudades["Bolivia"].count("Uyuni") == 1  # sin duplicados
    svc.update_session(sid, {**SESSION_FORM, "cliente": "ATC", "pais": "Bolivia", "ciudad": "Tupiza"})
    assert "Tupiza" in svc.data().ciudades["Bolivia"]
    page = client.get("/visitas/nueva").get_data(as_text=True)
    assert 'list="dl-ciudades"' in page and '<datalist id="dl-ciudades">' in page


def test_firmware_pendiente_de_confirmar_aceptado(app):
    sid = service(app).create_session({**SESSION_FORM, "firmware": S.PENDIENTE_CONFIRMAR})
    assert service(app).get_session(sid)["firmware"] == S.PENDIENTE_CONFIRMAR


def test_visita_anterior_conserva_valores_al_editar(app):
    svc = service(app)
    s = svc.get_session("SES-002")
    form = {k: s.get(k, "") for k in ("fecha", "hora", "responsable", "participantes", "cliente", "pais",
                                     "ciudad", "tipo_prueba", "objetivo", "fabricante", "modelo_maquina",
                                     "serial_maquina", "modelo_pos", "serial_pos", "firmware")}
    form["comercio"] = "Comercio trasladado"
    svc.update_session("SES-002", form)
    s2 = svc.get_session("SES-002")
    assert s2["cliente"] == s["cliente"] and s2["tipo_prueba"] == "Compatibilidad"
    assert s2["comercio"] == "Comercio trasladado"
    # Cambiar a un valor fuera de catálogo sí se rechaza.
    with pytest.raises(ValidationError):
        svc.update_session("SES-002", {**form, "tipo_prueba": "Diagnóstico"})


def test_formulario_incluye_selects_y_objetivos(client):
    page = client.get("/visitas/nueva").get_data(as_text=True)
    for valor in ("DATAFAST", "MEDIANET", "ATC", "PROMERICA CR", "13.0.11", "13.0.22",
                  "Nueva Integración", "Validación de correcciones", "Comercio / punto de venta"):
        assert valor in page
    texto = html_lib.unescape(page)
    assert '"ATC": "Bolivia"' in texto and '"Costa Rica": ["San José"' in texto
    assert "determinar si la combinación máquina–POS–versiones puede integrarse" in texto
    assert "ajustes y correcciones realizados por el comercio" in texto


def test_resumen_incluye_comercio(app):
    sid = service(app).create_session(SESSION_FORM)
    assert "Cliente / Comercio: DATAFAST - Comercio Piloto QA" in service(app).email_summary(sid)


def test_agregar_ciudad_y_cliente_con_pais(client, app):
    assert client.post("/configuracion/catalogo", {"catalogo": "ciudad", "valor": "Montañita",
                                                   "pais": "Ecuador"}).status_code == 302
    client.post("/configuracion/catalogo", {"catalogo": "cliente", "valor": "BANCO NUEVO", "pais": "Bolivia"})
    client.post("/configuracion/catalogo", {"catalogo": "ciudad", "valor": "Sin país"})
    data = service(app).data()
    assert "Montañita" in data.ciudades["Ecuador"]
    assert data.clientes_pais["BANCO NUEVO"] == "Bolivia"
    assert not any("Sin país" in v for v in data.ciudades.values())
    assert client.post("/configuracion/catalogo", {"catalogo": "cliente_pais", "valor": "X"}).status_code == 400
