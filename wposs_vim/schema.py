"""Esquema del libro WPOSS: hojas, columnas y catálogos.

Las columnas se localizan por el texto del encabezado (fila 1), no por su
posición, para tolerar que alguien reordene columnas en Excel. Las claves
internas (snake_case) son las que usa el resto de la aplicación.
"""

SHEET_INSTRUCCIONES = "Instrucciones"
SHEET_LISTAS = "Listas"
SHEET_ID = "Identificación y Versiones"
SHEET_REVISION = "Revisión Física y Eléctrica"
SHEET_CASOS = "Casos de Prueba"
SHEET_INCIDENCIAS = "Incidencias"
SHEET_CIERRE = "Cierre de Sesión"

# Hojas propias de la aplicación (se agregan a la copia de trabajo).
SHEET_APP_SESIONES = "App_Sesiones"
SHEET_APP_EVIDENCIAS = "App_Evidencias"
SHEET_APP_HISTORIAL = "App_Historial"
SHEET_APP_CONTADORES = "App_Contadores"
SHEET_APP_CHECKLIST = "App_Checklist"
SHEET_APP_CHECKLIST_RES = "App_Checklist_Resultados"

ORIGINAL_SHEETS = [
    SHEET_INSTRUCCIONES, SHEET_LISTAS, SHEET_ID, SHEET_REVISION,
    SHEET_CASOS, SHEET_INCIDENCIAS, SHEET_CIERRE,
]
APP_SHEETS = [SHEET_APP_SESIONES, SHEET_APP_EVIDENCIAS, SHEET_APP_HISTORIAL, SHEET_APP_CONTADORES,
              SHEET_APP_CHECKLIST, SHEET_APP_CHECKLIST_RES]

# (clave, encabezado exacto). Las marcadas como "added" no existen en el
# libro original y se agregan al final de la hoja durante la migración.
ID_COLUMNS = [
    ("sesion_id", "Sesión ID"),
    ("fecha", "Fecha"),
    ("hora", "Hora"),
    ("responsable", "Responsable"),
    ("participantes", "Participantes"),
    ("cliente", "Cliente / Piloto"),
    ("fabricante", "Fabricante máquina"),
    ("modelo_maquina", "Modelo máquina"),
    ("serial_maquina", "Serial máquina"),
    ("modelo_pos", "Modelo POS"),
    ("serial_pos", "Serial POS"),
    ("objetivo", "Objetivo de la sesión"),
    ("tipo_prueba", "Tipo de prueba"),
    ("firmware", "Firmware NEW5320"),
    ("mdb_estandar", "MDB — Estándar / Especificación"),
    ("mdb_version", "MDB — Versión de implementación"),
    ("mdb_modulo", "MDB — Módulo de software"),
    ("version_financiera", "Versión Financiera"),
    ("version_polaris", "Versión Agente Polaris"),
    ("configuraciones", "Configuraciones relevantes"),
    ("version_anterior", "Versión anterior (si aplica)"),
    ("version_nueva", "Versión nueva (si aplica)"),
    ("fecha_instalacion", "Fecha de instalación"),
    ("checksum", "Identificador de compilación / checksum"),
    ("compatibilidad", "Compatibilidad prevista"),
    ("observaciones", "Observaciones"),
    ("pais", "País"),
    ("ciudad", "Ciudad"),
    ("comercio", "Comercio / punto de venta"),
    ("codigo_fabricante", "Código del fabricante"),
    ("nivel_maquina", "Nivel de la máquina"),
    ("version_maquina", "Versión de la máquina"),
    ("version_gateway", "Versión gateway MDB"),
    ("mdb_resultado", "Prueba MDB — Resultado"),
    ("mdb_observacion", "Prueba MDB — Observaciones / error"),
    ("dex_resultado", "Prueba DEX — Resultado"),
    ("dex_archivo", "Prueba DEX — Archivo obtenido"),
    ("dex_customer_id", "Prueba DEX — Customer ID"),
    ("dex_provider_id", "Prueba DEX — Provider ID"),
    ("dex_observacion", "Prueba DEX — Observaciones / error"),
]
ID_ADDED = ["pais", "ciudad", "comercio", "codigo_fabricante", "nivel_maquina", "version_maquina",
            "version_gateway", "mdb_resultado", "mdb_observacion", "dex_resultado", "dex_archivo",
            "dex_customer_id", "dex_provider_id", "dex_observacion"]
# Campos del libro que el formulario ya no solicita; se conservan y se muestran si tienen datos.
ID_LEGACY_FIELDS = ["mdb_estandar", "mdb_version", "mdb_modulo", "version_anterior", "version_nueva",
                    "fecha_instalacion", "checksum", "compatibilidad"]

REVISION_COLUMNS = [
    ("sesion_id", "Sesión ID"),
    ("item", "Ítem de revisión"),
    ("resultado", "Resultado"),
    ("evidencia", "Evidencia"),
    ("observaciones", "Observaciones"),
]

CASOS_COLUMNS = [
    ("id", "ID de prueba"),
    ("sesion_id", "Sesión ID"),
    ("componente", "Componente"),
    ("tipo_verificacion", "Tipo de verificación"),
    ("objetivo", "Objetivo"),
    ("precondiciones", "Precondiciones"),
    ("procedimiento", "Procedimiento"),
    ("resultado_esperado", "Resultado esperado"),
    ("resultado_obtenido", "Resultado obtenido"),
    ("estado", "Estado"),
    ("evidencia", "Evidencia"),
    ("observaciones", "Observaciones"),
    ("responsable", "Responsable"),
    ("incidencia", "Incidencia asociada"),
    ("siguiente_accion", "Siguiente acción"),
]

INCIDENCIAS_COLUMNS = [
    ("id", "ID"),
    ("fecha", "Fecha"),
    ("sesion_id", "Sesión ID"),
    ("componente_version", "Componente y versión"),
    ("descripcion", "Descripción"),
    ("pasos", "Pasos para reproducir"),
    ("resultado_esperado", "Resultado esperado"),
    ("resultado_obtenido", "Resultado obtenido"),
    ("severidad", "Severidad / Prioridad"),
    ("evidencia", "Evidencia"),
    ("responsable", "Responsable"),
    ("ticket", "Ticket"),
    ("siguiente_accion", "Siguiente acción"),
    ("estado", "Estado"),
    ("resultado_reprueba", "Resultado de la reprueba"),
    ("prueba_id", "ID de prueba asociada"),
]
INCIDENCIAS_ADDED = ["prueba_id"]

CIERRE_COLUMNS = [
    ("sesion_id", "Sesión ID"),
    ("fecha_cierre", "Fecha de cierre"),
    ("fecha_visita", "Fecha de la visita"),
    ("cliente", "Cliente / Comercio"),
    ("fabricante", "Fabricante máquina"),
    ("modelo_maquina", "Modelo máquina"),
    ("serial_maquina", "Serial máquina"),
    ("modelo_pos", "Modelo POS"),
    ("serial_pos", "Serial POS"),
    ("firmware", "Firmware NEW5320"),
    ("mdb_estandar", "MDB — Estándar"),
    ("mdb_version", "MDB — Versión"),
    ("mdb_modulo", "MDB — Módulo"),
    ("version_financiera", "Versión Financiera"),
    ("version_polaris", "Versión Agente Polaris"),
    ("participantes", "Participantes"),
    ("responsable", "Responsable de la sesión"),
    ("objetivo", "Objetivo de la sesión"),
    ("total_planificadas", "Total planificadas"),
    ("total_ejecutadas", "Total ejecutadas"),
    ("aprobadas", "Aprobadas"),
    ("fallidas", "Fallidas"),
    ("bloqueadas", "Bloqueadas"),
    ("pendientes", "Pendientes"),
    ("incidencias_abiertas", "Incidencias abiertas"),
    ("versiones_cubiertas", "Versiones y equipos cubiertos"),
    ("pendientes_area", "Pendientes (Fabricante/Desarrollo/QA/Cliente)"),
    ("concepto", "Concepto final"),
    ("responsable_cierre", "Responsable del cierre"),
    ("resumen", "Resumen para correo"),
]
# Columnas del cierre que el usuario diligencia; el resto son fórmulas.
CIERRE_INPUT_KEYS = ["sesion_id", "fecha_cierre", "versiones_cubiertas",
                     "pendientes_area", "concepto", "responsable_cierre"]

APP_SESIONES_COLUMNS = [
    ("sesion_id", "Sesión ID"),
    ("estado_registro", "Estado de registro"),
    ("creado", "Creado"),
    ("modificado", "Modificado"),
    ("origen", "Origen"),
]
APP_EVIDENCIAS_COLUMNS = [
    ("id", "ID"),
    ("sesion_id", "Sesión ID"),
    ("tipo_registro", "Tipo de registro"),
    ("registro_id", "ID de registro"),
    ("archivo", "Archivo"),
    ("ruta", "Ruta relativa"),
    ("tamano", "Tamaño (bytes)"),
    ("sha256", "SHA-256"),
    ("tipo_archivo", "Tipo de archivo"),
    ("descripcion", "Descripción"),
    ("advertencia", "Advertencia"),
    ("fecha", "Fecha de carga"),
    ("categoria", "Categoría"),
]
APP_EVIDENCIAS_ADDED = ["categoria"]
APP_HISTORIAL_COLUMNS = [
    ("fecha", "Fecha"),
    ("tipo_registro", "Tipo de registro"),
    ("registro_id", "ID de registro"),
    ("sesion_id", "Sesión ID"),
    ("campo", "Campo"),
    ("anterior", "Valor anterior"),
    ("nuevo", "Valor nuevo"),
    ("accion", "Acción"),
]
# Plantilla de checklist por tipo de prueba (gestionable desde la interfaz).
APP_CHECKLIST_COLUMNS = [
    ("id", "ID"),
    ("tipo", "Tipo de prueba"),
    ("seccion", "Sección"),
    ("orden", "Orden"),
    ("texto", "Ítem"),
    ("activo", "Activo"),
]
# Resultado de cada ítem en una visita. El texto se copia al crear la visita para que los
# cambios posteriores de la plantilla no alteren el histórico.
APP_CHECKLIST_RES_COLUMNS = [
    ("sesion_id", "Sesión ID"),
    ("item_id", "ID ítem"),
    ("tipo", "Tipo de prueba"),
    ("seccion", "Sección"),
    ("orden", "Orden"),
    ("texto", "Ítem"),
    ("resultado", "Resultado"),
    ("observacion", "Observación"),
    ("fecha", "Fecha"),
]
APP_CONTADORES_COLUMNS = [
    ("prefijo", "Prefijo"),
    ("ultimo", "Último número"),
]

SHEET_COLUMNS = {
    SHEET_ID: ID_COLUMNS,
    SHEET_REVISION: REVISION_COLUMNS,
    SHEET_CASOS: CASOS_COLUMNS,
    SHEET_INCIDENCIAS: INCIDENCIAS_COLUMNS,
    SHEET_CIERRE: CIERRE_COLUMNS,
    SHEET_APP_SESIONES: APP_SESIONES_COLUMNS,
    SHEET_APP_EVIDENCIAS: APP_EVIDENCIAS_COLUMNS,
    SHEET_APP_HISTORIAL: APP_HISTORIAL_COLUMNS,
    SHEET_APP_CONTADORES: APP_CONTADORES_COLUMNS,
    SHEET_APP_CHECKLIST: APP_CHECKLIST_COLUMNS,
    SHEET_APP_CHECKLIST_RES: APP_CHECKLIST_RES_COLUMNS,
}

# Encabezados de la hoja Listas (catálogos). Los tres últimos se agregan.
CATALOGS = [
    ("estados", "Estados"),
    ("severidad", "Severidad"),
    ("tipo_verificacion", "Tipo de verificación"),
    ("componente", "Componente"),
    ("tipo_prueba", "Tipo de prueba (sesión)"),
    ("estado_incidencia", "Estado de incidencia"),
    ("concepto", "Concepto final"),
    ("pais", "País"),
    ("fabricante", "Fabricante máquina"),
    ("item_revision", "Ítem de revisión física"),
    ("cliente", "Cliente WPOSS"),
    ("cliente_pais", "País del cliente"),
    ("ciudad", "Ciudad"),
    ("ciudad_pais", "País de la ciudad"),
    ("firmware", "Firmware NEW5320"),
    ("nivel_maquina", "Nivel de la máquina"),
    ("resultado_prueba", "Resultado de prueba MDB / DEX"),
]
CATALOGS_ADDED = ["pais", "fabricante", "item_revision", "cliente", "cliente_pais",
                  "ciudad", "ciudad_pais", "firmware", "nivel_maquina", "resultado_prueba"]
CATALOG_LABELS = dict(CATALOGS)

# Columnas de Listas que acompañan fila a fila a otro catálogo (no son listas propias).
CATALOG_PAIRS = {"cliente": "cliente_pais", "ciudad": "ciudad_pais"}
CATALOGS_HIDDEN = list(CATALOG_PAIRS.values())

# Catálogos cuyos valores no deben ampliarse desde la interfaz porque la
# lógica de cálculo del cierre depende de ellos (fórmulas del libro).
CATALOGS_FIXED = ["estados", "estado_incidencia", "concepto"]

# Valores semilla de los catálogos nuevos. Los ítems de revisión y los
# fabricantes salen del libro original; el resto los definió WPOSS.
SEED_PAISES = ["Ecuador", "Costa Rica", "Bolivia"]
# Lista de países de la versión anterior de la aplicación; si el libro aún la
# tiene sin cambios, se reemplaza por los países con clientes de WPOSS.
LEGACY_SEED_PAISES = ["Colombia", "Ecuador", "Perú", "Panamá", "México", "Chile",
                      "Guatemala", "Costa Rica", "República Dominicana", "Otro"]
SEED_CLIENTES = [("DATAFAST", "Ecuador"), ("MEDIANET", "Ecuador"), ("ATC", "Bolivia"),
                 ("PROMERICA CR", "Costa Rica")]
SEED_CIUDADES = {
    "Ecuador": ["Quito", "Guayaquil", "Cuenca", "Santo Domingo", "Machala", "Manta", "Durán",
                "Portoviejo", "Ambato", "Loja", "Riobamba", "Esmeraldas", "Ibarra", "Quevedo",
                "Milagro", "Latacunga", "Babahoyo", "Santa Elena", "Tulcán", "Guaranda", "Azogues",
                "Nueva Loja", "Puerto Francisco de Orellana", "Tena", "Puyo", "Macas", "Zamora",
                "Puerto Baquerizo Moreno"],
    "Costa Rica": ["San José", "Alajuela", "Cartago", "Heredia", "Liberia", "Puntarenas", "Limón"],
    "Bolivia": ["La Paz", "El Alto", "Santa Cruz de la Sierra", "Cochabamba", "Sucre", "Oruro",
                "Potosí", "Tarija", "Trinidad", "Cobija"],
}
SEED_FIRMWARE = ["13.0.11", "13.0.13", "13.0.14", "13.0.15", "13.0.17", "13.0.22"]
# Nivel MDB de la VMC (feature level). Ampliable desde Configuración.
SEED_NIVELES = ["Nivel 1", "Nivel 2", "Nivel 3"]
RESULTADO_FALLIDA = "Fallida"
SEED_RESULTADOS = ["Exitosa", RESULTADO_FALLIDA, "No realizada", "No aplica"]
DEX_ARCHIVO_OPCIONES = ["Sí", "No"]

# Tipos de prueba de la sesión. Reemplazan a los del libro original por decisión de WPOSS;
# los registros existentes conservan su valor.
TIPOS_PRUEBA = ["Nueva Integración", "Reintegración", "Validación de correcciones",
                "Integración de seguimiento"]
LEGACY_TIPOS_PRUEBA = ["Instalación", "Diagnóstico", "Compatibilidad", "Piloto",
                       "Actualización de versión", "Regresión", "Otro"]

# Validaciones de lista del libro original (hoja, columna, catálogo).
# openpyxl elimina las validaciones de extensión x14 al guardar, por eso
# se regeneran en cada escritura como validaciones estándar equivalentes.
DATA_VALIDATIONS = [
    (SHEET_ID, "tipo_prueba", "tipo_prueba"),
    (SHEET_ID, "pais", "pais"),
    (SHEET_ID, "ciudad", "ciudad"),
    (SHEET_ID, "cliente", "cliente"),
    (SHEET_ID, "firmware", "firmware"),
    (SHEET_ID, "nivel_maquina", "nivel_maquina"),
    (SHEET_ID, "mdb_resultado", "resultado_prueba"),
    (SHEET_ID, "dex_resultado", "resultado_prueba"),
    (SHEET_REVISION, "resultado", "estados"),
    (SHEET_CASOS, "componente", "componente"),
    (SHEET_CASOS, "tipo_verificacion", "tipo_verificacion"),
    (SHEET_CASOS, "estado", "estados"),
    (SHEET_INCIDENCIAS, "severidad", "severidad"),
    (SHEET_INCIDENCIAS, "estado", "estado_incidencia"),
    (SHEET_CIERRE, "concepto", "concepto"),
]
DV_MAX_ROW = 2000

# Valores con significado en el cálculo del cierre (fórmulas originales).
ESTADO_APROBADO = "Aprobado"
ESTADO_FALLIDO = "Fallido"
ESTADO_BLOQUEADO = "Bloqueado"
ESTADO_PENDIENTE = "Pendiente"
INCIDENCIA_ABIERTA = "Abierto"
INCIDENCIA_CERRADA = "Cerrado"
CONCEPTO_APTO = "Apto para piloto"
CONCEPTO_CONDICIONES = "Apto con condiciones"
CONCEPTO_NO_APTO = "No apto"
CONCEPTO_PENDIENTE = "Pendiente"

ESTADO_REGISTRO_BORRADOR = "Borrador"
ESTADO_REGISTRO_EN_CURSO = "En curso"
ESTADO_REGISTRO_CERRADA = "Cerrada"

PENDIENTE_CONFIRMAR = "Pendiente de confirmar"
EXAMPLE_MARKER = "fila de ejemplo"

# Colores del libro original.
COLOR_CALC = "FFE2EFEA"   # celda calculada (verde claro)


# Checklist inicial de "Nueva Integración" (definido por WPOSS). Se carga una sola vez al
# crear la hoja App_Checklist; después se gestiona desde la interfaz.
SEED_CHECKLIST = {
    "Nueva Integración": [
        ("Preguntas iniciales", [
            "Verificar los implementos necesarios para la visita: 2 cables MDB, 2 cables DEX, PC, "
            "dispositivo 5320 con su cargador, multímetro y Sniffer Qibixx.",
            "Validar que el terminal 5320 tenga instalada la versión de firmware más reciente.",
            "Confirmar la disponibilidad de dos terminales: uno en modo release y otro en debug.",
            "Asegurar que el SwitchMode del dispositivo esté configurado en Host Mode.",
            "Verificar que la máquina cuente con sensores de caída y/o permita realizar operaciones con la "
            "puerta abierta.",
            "Realizar la conexión del dispositivo a la máquina expendedora con la máquina VMC apagada.",
            "Confirmar que la máquina tenga los productos configurados correctamente.",
            "Verificar que el terminal tenga instaladas las aplicaciones MDB y Financiera.",
        ]),
        ("Prueba terminal 5320", [
            "Verificar que la aplicación MDB y la máquina expendedora establezcan conexión correctamente.",
            "Realizar ventas exitosas y validar que el producto se dispense correctamente.",
            "Realizar una prueba de venta cancelada desde la aplicación y confirmar que la cancelación se "
            "refleje en la VMC.",
            "Ejecutar ventas en los tres niveles configurados en los ajustes generales.",
            "Revisar que el precio del producto coincida con el valor recibido en el dispositivo.",
        ]),
    ],
}
CHECKLIST_ACTIVO = "Sí"
CHECKLIST_INACTIVO = "No"
