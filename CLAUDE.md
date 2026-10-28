# CLAUDE.md

Este archivo proporciona orientación a Claude Code (claude.ai/code) al trabajar con el código de este repositorio.

## Comandos

```bash
abrir_plataforma.bat                # Windows: crea .venv si falta, inicia el servidor minimizado si no responde y abre el navegador
abrir_plataforma.bat --no-browser   # Igual, sin abrir el navegador (útil para pruebas)
iniciar.bat                         # Windows: crea .venv (solo la primera vez) e inicia la app en consola visible
python app.py                       # Inicia en http://127.0.0.1:5000 y abre el navegador
python app.py --no-browser          # Inicia sin abrir el navegador
python -m pytest                    # Todas las pruebas (~180 s; 73 pruebas)
python -m pytest tests/test_sesiones.py::test_02_crear_sesion   # Prueba individual
python -m pytest -k "cierre"        # Pruebas por palabra clave
```

**Entorno:** Windows, Python 3.10+ (probado con 3.10 y 3.11; `.venv` usa 3.11). Dependencias en `requirements.txt`: Flask 3.1, openpyxl 3.0.9, Waitress 3.0, pytest. Sin CDN ni servicios externos: la app debe funcionar sin internet.

**PyCharm:** `.idea/` define el intérprete `Python 3.11 (Integraciones VMC)` y las ejecuciones `WPOSS App` y `Pruebas (pytest)`.

**Requisito local:** el libro `WPOSS_Checklist_Pruebas_Vending_5320.xlsx` debe estar en la raíz. No se versiona (contiene datos de clientes). Sin él, `create_app()` lanza `StoreError`.

## Descripción

Aplicación web local (Flask + Jinja2 + CSS/JS propios) para registrar y cerrar visitas técnicas de integración de máquinas vending con el POS NEW5320. El almacenamiento es un libro Excel `.xlsx` basado en el checklist WPOSS. Interfaz en español. Volumen esperado: ~10 visitas/mes, un único equipo.

El análisis completo del libro original (hojas, relaciones, fórmulas, validaciones, riesgos) está en `docs/ANALISIS_EXCEL.md`. Leerlo antes de tocar la capa de datos o los cálculos de cierre.

### Estructura de módulos (`wposs_vim/`)

| Módulo | Rol |
|---|---|
| `__init__.py` | `create_app(base_dir, config_overrides, testing)`: carga config, crea carpetas, inicializa el libro, registra el blueprint y reintenta cambios pendientes. Todo se publica en `app.extensions["wposs"]` (`config`, `paths`, `store`, `service`, `evidence`, `backups`, `base_dir`). |
| `config.py` | `DEFAULT_CONFIG`, `load_config` (crea `config.json` si falta, fusiona con valores por defecto), `save_config` (escritura atómica), `Paths`. |
| `schema.py` | Nombres de hojas, columnas `(clave, encabezado)`, catálogos, validaciones a regenerar y constantes de estados/conceptos. Fuente única del esquema. |
| `excel_store.py` | **Capa única de acceso al Excel**: `ExcelStore`, `Sheet`, migración `ensure_schema`, `apply_validations`, fórmulas del cierre, diario de pendientes, `validate_workbook_file`. |
| `operations.py` | Operaciones de escritura serializables registradas en `Operations.REGISTRY`. |
| `validators.py` | `ValidationError(errors: dict)`, limpieza y validación por entidad. |
| `services.py` | Lógica de negocio: enriquecimiento de sesiones, generación de IDs, totales y evaluación del cierre, resumen para correo, dashboard y consultas. |
| `evidence.py` | Carpeta por visita y archivos adjuntos: categorías → subcarpetas (`CATEGORIES`), nombres seguros, sin sobrescritura, detección de números de tarjeta (Luhn), visor de texto y archivos copiados manualmente. |
| `backups.py` | Respaldos `auto_`/`manual_`/`previo_restauracion_`, retención y restauración validada. |
| `reports.py` | Exportación a un libro nuevo en `data/exportaciones/`; `report_context` (datos completos de una visita), `generate_visit_report` (informe HTML en `informes/`) y `build_visit_zip` (carpeta + informe + `datos_visita.xlsx`). |
| `security.py` | Acceso solo loopback, validación de Host, CSRF, cabeceras CSP, filtro de redacción en logs. |
| `routes.py` | Blueprint `main` con todas las rutas y el manejo de errores de escritura. |

### Almacenamiento y rutas de datos

| Ruta | Contenido |
|---|---|
| `WPOSS_Checklist_Pruebas_Vending_5320.xlsx` | Original de referencia. **Nunca se escribe.** |
| `data/original/` | Copia íntegra del original + `ORIGEN.txt` con SHA-256. |
| `data/trabajo/WPOSS_Vending_Datos.xlsx` | Libro de trabajo: almacenamiento real. |
| `data/evidencias/<SES-xxx>/` | Carpeta de la visita con subcarpetas `fotos/`, `logs/` (con `logs/new5320/` y `logs/qibixx/`), `videos/`, `documentos/`, `informes/`, `otros/`. |
| `data/papelera/<SES-xxx>/` | Archivos eliminados de una visita (`AAAAMMDD_HHMMSS__subcarpeta__nombre`). |
| `data/pendientes/*.json` | Diario de cambios no escritos (Excel bloqueado). |
| `data/.secret_key` | Clave de sesión Flask generada localmente. |
| `respaldos/`, `logs/app.log` | Respaldos y registro de operaciones. |

`data/`, `respaldos/` y `logs/` no se versionan.

### Libro de trabajo

Hojas originales: `Instrucciones`, `Listas` (oculta), `Identificación y Versiones`, `Revisión Física y Eléctrica`, `Casos de Prueba`, `Incidencias`, `Cierre de Sesión`. Todas se relacionan por `Sesión ID` (`SES-NNN`).

La migración `ensure_schema()` (idempotente, se ejecuta en cada escritura) agrega **sin modificar celdas existentes**:

- Columnas al final: `País`, `Ciudad`, `Comercio / punto de venta`, `Código del fabricante`, `Nivel de la máquina`, `Versión de la máquina`, `Versión gateway MDB` y las de `Prueba MDB — …` / `Prueba DEX — …` (Identificación); `ID de prueba asociada` (Incidencias).
- Catálogos al final de `Listas`: `País`, `Fabricante máquina`, `Ítem de revisión física`, `Cliente WPOSS` + `País del cliente`, `Ciudad` + `País de la ciudad` (pares fila a fila, `CATALOG_PAIRS`, leídos con `read_pairs`) y `Firmware NEW5320`, `Nivel de la máquina` (Nivel 1-3) y `Resultado de prueba MDB / DEX`.
- `_replace_catalog` sustituye `País` (lista anterior de la app) y `Tipo de prueba (sesión)` (`Listas!E`, valores originales del checklist) por las listas definidas por WPOSS **solo si conservan exactamente los valores anteriores**; deja historial y `initialize()` crea un respaldo antes de guardar la migración.
- Columna `Categoría` al final de `App_Evidencias` (si la hoja ya existía sin ella).
- Hojas: `App_Sesiones` (estado de registro Borrador/En curso/Cerrada), `App_Evidencias`, `App_Historial` (cambios campo a campo), `App_Contadores` (último número emitido por prefijo).
- Filas en `App_Sesiones` para sesiones preexistentes.

### Flujo de escritura

1. La ruta llama a un método de `Service` (nunca escribe directamente).
2. `Service` valida con `validators.py`, genera IDs con `next_id()` y arma operaciones `[(nombre, payload)]`.
3. `ExcelStore.write(ops, descripcion)` bajo `RLock`:
   - Reaplica primero las entradas de `data/pendientes/`.
   - `_check_writable()`: falla si existe `~$<nombre>` o si el archivo no se puede abrir en `r+b`.
   - `before_write` → `BackupManager.maybe_auto()`.
   - Carga el libro con `open_workbook()`, aplica `ensure_schema` y las operaciones.
   - `_save_atomic()`: `apply_validations`, `fullCalcOnLoad = True`, guarda en `.tmp_*.xlsx`, verifica las hojas y reemplaza con `os.replace`.
4. Si el libro está bloqueado → `ExcelLockedError` → las operaciones se guardan como **una sola entrada** del diario → `PendingWriteError`. Las rutas lo traducen con `_write_errors()` a un aviso "El cambio NO se guardó".
5. Entradas pendientes que fallan al reaplicarse se mueven a `data/pendientes/fallidos/`.

### Generación de IDs

`Service.next_id(prefijo)` = máximo entre los IDs existentes (sesiones, pruebas, incidencias, evidencias), `App_Contadores` y los IDs presentes en el diario de pendientes, + 1, con 3 dígitos mínimo. Los números nunca se reutilizan. Prefijos de prueba por componente en `config.json` → `pruebas.prefijos` (POS, MDB, FIN, AGP, VEN, MAQ, OTR); evidencias `EVD`; incidencias `INC`; sesiones `SES`. Los métodos que generan IDs y escriben mantienen `store._lock` durante todo el ciclo.

### Cálculos del cierre (equivalentes a las fórmulas S:Y y AD del libro)

`Service.totals(sid)`:

| Total | Regla (idéntica a la fórmula del libro) |
|---|---|
| planificadas | Pruebas de la sesión |
| ejecutadas | Estado distinto de `Pendiente` y de vacío (**incluye "No aplica" y "En observación"**) |
| aprobadas/fallidas/bloqueadas/pendientes | Conteo exacto del estado |
| incidencias_abiertas | Estado no vacío y distinto de `Cerrado` |

`Service.email_summary()` reproduce el texto de la fórmula `AD` ("Resumen de visita — Sesión …"), con una diferencia: la línea "Cliente / Comercio" usa `client_label()` (`CLIENTE - Comercio`), mientras la fórmula de Excel solo muestra la columna Cliente. `operations.save_cierre` escribe solo las columnas de captura (`CIERRE_INPUT_KEYS`) y restituye las fórmulas originales con `cierre_formulas(row)`.

`Service.evaluate_closure()` aplica los criterios de `config.json` → `cierre`. El libro **no define** criterios de salida (pregunta abierta en `Instrucciones` A38); los valores por defecto son conservadores y `componentes_criticos` está vacío a propósito. El concepto sugerido es orientativo; `save_cierre` bloquea "Apto para piloto" si hay bloqueos y exige pendientes documentados para "Apto con condiciones".

### Filas de ejemplo

Se detectan por el texto `fila de ejemplo` (`schema.EXAMPLE_MARKER`): una sesión es ejemplo si su campo Observaciones lo contiene (SES-001); una incidencia es ejemplo si su sesión lo es o su Descripción lo contiene (INC-001..003). Con `datos.excluir_ejemplos = true` se excluyen de dashboard, listados y totales. Las fórmulas de Excel sí las cuentan; la pantalla de cierre muestra la diferencia. Solo se eliminan por acción explícita (`delete_example`), que vacía la fila y deja el contenido en `App_Historial`.

### Listas de la visita (definidas por WPOSS)

- Cliente, país, ciudad y firmware son selects alimentados por `Listas`; `validate_session(data, catalogos, draft, ciudades, current)` exige que la ciudad pertenezca al país y acepta el valor que ya tenía el registro (`current`) aunque ya no esté en el catálogo, para no forzar cambios en visitas anteriores.
- `Data.clientes_pais` y `Data.ciudades` alimentan los selects; el formulario recibe los mapas como JSON en atributos `data-country-map`, `data-city-map` y `data-objective-map` (`app.js`).
- Objetivo por tipo de prueba: `config.json` → `sesiones.objetivos_por_tipo` (`Service.objective_templates`). El JS solo lo escribe si el campo está vacío o contiene otro texto de plantilla.
- Clientes y ciudades se agregan en Configuración con su país (`add_catalog_value` con `pair`). Las columnas de país emparejadas (`CATALOGS_HIDDEN`) no se editan solas.
- `rec["cliente_label"]` (cliente y comercio) es lo que muestran listados, carpeta e informe.
- Paso 4 del formulario: **Pruebas MDB y DEX** (`mdb_resultado`/`mdb_observacion`, `dex_resultado`/`dex_archivo`/`dex_customer_id`/`dex_provider_id`/`dex_observacion`). Resultado `Fallida` exige la observación (`validate_session`).
- `S.ID_LEGACY_FIELDS` (MDB estándar/versión/módulo, versión anterior/nueva, fecha de instalación, checksum, compatibilidad) ya no están en el formulario: `update_session` conserva su valor si no llegan en el envío y `Service.legacy_fields()` los muestra cuando tienen datos. El resumen usa la línea `MDB:` original solo si la visita tiene esos campos; si no, `Versión de la máquina | Gateway MDB`, más las líneas `Prueba MDB/DEX`.
- Categoría `Archivo DEX` → `logs/dex/` (extensión `.dex` tratada como texto).

### Carpetas de visitas, evidencias e informes

- `EvidenceManager.ensure_session_dir()` crea la carpeta de la visita con sus subcarpetas al crear la sesión.
- Logs por origen: categoría `Log del POS NEW5320` → `logs/new5320/`, `Log de Qibixx` → `logs/qibixx/`, `Log de la visita` → `logs/`, `Archivo DEX` → `logs/dex/`. `folder_of()` devuelve el primer nivel (`logs`) y `subfolder_of()` la ruta completa; `LOG_SUBFOLDERS` define las subcarpetas válidas para `?sub=`. Un archivo copiado a mano en `logs/qibixx/` sugiere su categoría por la ruta (`category_for_path`).
- La categoría decide la subcarpeta y el prefijo del nombre (`evidence.CATEGORIES`); las fotos exigen extensión de imagen, los videos `mp4/mov`. Sin categoría se infiere por extensión (`infer_category`), también para registros antiguos sin columna `Categoría`.
- `Service.create_session(form, draft, files)` valida todos los archivos antes de crear nada, los guarda en disco y escribe sesión + `add_evidence` en **una sola** llamada a `store.write`. Si la escritura falla (salvo `PendingWriteError`), borra los archivos recién guardados (`_write_with_files`). Con el libro bloqueado los archivos se conservan y su registro queda en el diario.
- Los IDs `EVD-NNN` de varios archivos se asignan consecutivos desde un único `next_id` (`_store_files`).
- Eliminar evidencia (`Service.delete_evidence`, ruta `POST /carpetas/<sid>/eliminar` con `confirmar=si`): mueve el archivo a la papelera (`EvidenceManager.move_to_trash`) y luego ejecuta la operación `delete_evidence`, que vacía la fila de `App_Evidencias`, quita la ruta de la columna Evidencia del registro asociado y deja historial con la ubicación en la papelera. Si la escritura falla (salvo `PendingWriteError`), `restore_from_trash` devuelve el archivo. Nunca borrar archivos de evidencia de forma definitiva.
- Antes de guardar, `app.js` gestiona todos los `input[type=file][multiple]`: lista con miniatura (`blob:`, permitido en `img-src`), botón Quitar y acumulación de selecciones reconstruyendo `input.files` con `DataTransfer`.
- `/archivo/<ruta>` solo sirve rutas registradas en `App_Evidencias`. Únicamente los HTML con categoría `Informe generado` se muestran como HTML; cualquier otro `.html` se sirve como texto.
- `_expediente.html` es compartido por la vista de carpeta y por `informe_visita.html` (HTML autónomo con CSS en línea, sin scripts). Recibe `file_link(ruta)`: URL de la app en la carpeta, ruta relativa (`posixpath.relpath`) en el informe y en el .zip. No usar `url_for` ni `request` dentro de `_expediente.html`.

### Rutas principales

| Ruta | Función |
|---|---|
| `/` | Dashboard con filtros |
| `/visitas`, `/visitas/nueva`, `/visitas/<sid>`, `/visitas/<sid>/editar` | Listado, alta por pasos (borrador), ficha con pestañas, edición |
| `/visitas/<sid>/revision[/iniciar]` | Revisión física y eléctrica |
| `/pruebas`, `/pruebas/nueva`, `/pruebas/<id>/editar` | Casos de prueba |
| `/incidencias`, `/incidencias/nueva?prueba=<id>`, `/incidencias/<id>/editar` | Incidencias (precarga desde prueba) |
| `/cierre`, `/visitas/<sid>/cierre`, `/visitas/<sid>/resumen.txt`, `/visitas/<sid>/informe` | Cierre, resumen para correo, informe imprimible |
| `/visitas/<sid>/evidencias` (POST, varios archivos), `/archivo/<ruta>` | Subida y descarga de evidencias registradas |
| `/carpetas`, `/carpetas/<sid>[?sub=fotos\|logs…][?vista=expediente]`, `/carpetas/<sid>/ver?ruta=` | Carpetas de visitas, archivos por subcarpeta, todos los datos, visor de logs |
| `/carpetas/<sid>/informe`, `/reportes/informe` (POST), `/carpetas/<sid>/descargar`, `/carpetas/<sid>/abrir`, `/carpetas/<sid>/registrar`, `/carpetas/<sid>/eliminar` | Generar informe, descargar .zip, abrir en Explorador, registrar archivo copiado, eliminar archivo a la papelera |
| `/maquinas`, `/identificacion`, `/revision`, `/reportes`, `/reportes/comparar`, `/reportes/exportar` | Consultas y reportes |
| `/configuracion`, `/respaldos/*`, `/pendientes/reintentar` | Configuración, respaldos, cambios pendientes |

## Restricciones técnicas críticas

- **Nunca llamar `load_workbook(ruta)` directamente.** Usar `excel_store.open_workbook()`, que carga desde memoria. Con Python 3.11 + openpyxl 3.0.9 el archivo queda abierto hasta la recolección de basura y Windows impide el `os.replace` posterior.
- **Escribir texto con `set_cell()`** (o `Sheet.write`), nunca `cell.value = texto`: fuerza el tipo texto para que un valor que empieza con `=` no se guarde como fórmula.
- **No insertar ni reordenar columnas** en las hojas originales. Las fórmulas del cierre referencian columnas por letra (`Identificación!B..S`, `Casos!B` y `J`, `Incidencias!C` y `N`). Las columnas nuevas solo se agregan al final mediante `_add_columns` y se declaran en `schema.py` (lista `*_ADDED`).
- **Las columnas se localizan por encabezado**, no por posición. Un cambio de encabezado en `schema.py` debe coincidir exactamente con el libro.
- **openpyxl elimina las validaciones x14** del original. `apply_validations()` las regenera en cada guardado a partir de `schema.DATA_VALIDATIONS`; una lista desplegable nueva se agrega ahí.
- **openpyxl no recalcula fórmulas.** Todo valor calculado que muestre la app se calcula en Python.
- **No modificar** `Instrucciones`, ni celdas, fórmulas o formatos ajenos al registro que se escribe.
- Los catálogos `estados`, `estado_incidencia` y `concepto` son fijos (`CATALOGS_FIXED`): los cálculos dependen de sus valores exactos.
- Una prueba nunca se aprueba automáticamente. Editar una prueba nunca cierra sus incidencias.
- **CSP:** `script-src 'self'`. No usar `<script>` en línea ni manejadores `onclick`; todo el JS va en `static/js/app.js` con atributos `data-*`.
- Todo formulario POST incluye `{{ m.csrf() }}`. Las plantillas importan macros con `{% import "_macros.html" as m with context %}` (sin `with context` no ven `csrf_token` ni `request`).
- Flask corre sin modo debug: tras cambiar plantillas o estáticos hay que **reiniciar el servidor**.
- El servidor solo escucha en `127.0.0.1`; `security.install` rechaza IP y cabecera Host no locales.
- Scripts `.bat`: guardar con fin de línea CRLF y solo caracteres ASCII. Para esperas no usar `ping 127.0.0.1` (en este equipo el ICMP local tarda ~14 s y falla); la espera de arranque la hace `curl.exe --retry-connrefused`.

## Reglas de desarrollo

### Regla 1: Nuevos campos, hojas u operaciones

Toda ampliación de datos sigue el patrón de capas del proyecto; ninguna capa puede omitirse:

| Paso | Ubicación |
|---|---|
| Declarar columnas/hoja/catálogo | `schema.py` (y `*_ADDED` / `APP_SHEETS` / `CATALOGS_ADDED` si no existen en el original) |
| Migración idempotente | `excel_store.ensure_schema()` |
| Escritura | Función en `operations.py`, registrada en `Operations.REGISTRY`, payload serializable a JSON, valida precondiciones antes de mutar y registra cambios con `_history()` |
| Validación | `validators.py` |
| Lógica y orquestación | Método en `Service`; es lo único que las rutas invocan |
| Interfaz | Ruta en `routes.py` con manejo de `ValidationError` y `StoreError` vía `_write_errors()`; plantilla con macros de `_macros.html` |
| Pruebas | Caso en `tests/` que verifique persistencia real en el libro |

Las rutas y plantillas no acceden a `ExcelStore` ni a openpyxl directamente (excepciones existentes: subida de evidencias, catálogos y respaldos en `routes.py`).

### Regla 2: Integridad de datos

- No eliminar ni modificar información existente del libro sin una decisión explícita del usuario.
- No inventar campos técnicos, versiones, resultados ni criterios de aceptación no respaldados por el libro o por un requisito explícito. Si falta un criterio, documentarlo y hacerlo configurable.
- Nunca informar que un cambio se guardó si quedó en el diario de pendientes.
- Ante una ambigüedad que afecte datos o resultados, señalarla y no modificar datos irreversiblemente.

### Regla 3: Datos sensibles y privacidad

- El libro original y `data/` contienen datos reales de clientes: **nunca se versionan** ni se copian a documentación, pruebas o mensajes de commit.
- Las pruebas usan exclusivamente `tests/fixtures/checklist_anonimizado.xlsx` (misma estructura y fórmulas, datos ficticios). Si se regenera, verificar que no queden nombres, seriales ni metadatos (`lastModifiedBy`) reales.
- No registrar en logs ni evidencias números de tarjeta, claves, credenciales ni datos financieros. `RedactFilter` enmascara secuencias tipo PAN; no desactivarlo.
- Las pruebas trabajan en `tmp_path`; nunca contra `data/` real.

### Regla 4: Textos de la interfaz

- Todo texto visible para el usuario se redacta en español, con ortografía correcta, redacción profesional y terminología consistente con el libro WPOSS (Sesión ID, Concepto final, Apto para piloto, etc.).
- Los estados se expresan con etiqueta y texto (`m.badge`), nunca solo con color.
- Diseño: minimalista y sobrio. Un único color de acento (`--accent`), verde/ámbar/rojo solo para estados, bordes finos y sombras sutiles. Usar los tokens de `:root` en `app.css`; no introducir frameworks CSS, CDN ni fuentes externas.

### Regla 5: Documentación y comentarios en Python

- Módulos y clases llevan docstring breve con su responsabilidad. Las funciones llevan docstring cuando su propósito o una regla de negocio no sea evidente por el nombre.
- No agregar comentarios dentro de funciones salvo para aclarar una decisión de negocio, una restricción técnica o una lógica no evidente.
- No se permite el uso de emojis en docstrings, comentarios, logs, mensajes técnicos ni documentación.

### Regla 6: Uso de Git

Queda prohibido realizar acciones que modifiquen el repositorio mediante Git sin una solicitud explícita.

No se deberá: crear commits, realizar push, crear tags, crear ramas, realizar merges, realizar rebases ni ejecutar cualquier operación que modifique el historial o el estado del repositorio.

Git solo podrá utilizarse para consulta y análisis: revisar cambios, consultar archivos modificados, ver diferencias, analizar commits, revisar ramas, consultar stashes e inspeccionar el estado del repositorio.

Remoto: `origin` → `https://github.com/JhonJaAscanio/IntegracionesVMC.git` (público), rama `main`.

### Regla 7: Generación de mensajes de commit y uso controlado de Git

Cuando se solicite la generación de un mensaje de commit, se deberá analizar el contexto y revisar los cambios mediante Git (`git status`, `git diff`, `git diff --cached`) para identificar con precisión las modificaciones, y entregar tanto el título como la descripción.

#### Formato obligatorio

- La primera línea contiene un título propuesto acorde a los cambios: en español, en modo imperativo, de máximo 72 caracteres y sin punto final, que resuma el propósito principal del commit.
- Si el usuario proporciona un título o identificador, se usa ese en lugar del propuesto.
- Una línea en blanco separa el título de la descripción.
- Cada cambio se describe en una línea independiente con el prefijo `-`.

#### Redacción

- Tercera persona, lenguaje técnico y profesional.
- Sin primera persona, emojis ni abreviaturas informales.
- Cada punto describe una modificación real y verificable. No inventar cambios.

#### Restricción de ejecución

La generación de un mensaje de commit no autoriza ejecutar comandos Git que modifiquen el repositorio. Por defecto solo se entrega el texto. `git add`, `git commit`, `git push`, `git merge`, `git rebase`, `git tag` y la creación o eliminación de ramas permanecen prohibidos según la Regla 6.

#### Doble confirmación obligatoria

Incluso si el usuario solicita explícitamente un commit o una acción que modifique el repositorio, se deberá pedir una segunda confirmación antes de ejecutar cualquier comando, indicando que:

- Se va a modificar el repositorio.
- La acción está protegida por las reglas del proyecto.
- Se requiere autorización final antes de continuar.

Antes de cualquier push se debe verificar que no se incluyan `data/`, respaldos, logs, `.venv`, la clave de sesión ni el libro original.

### Regla 8: Idioma de comunicación con el usuario

Toda comunicación con el usuario deberá realizarse obligatoriamente en español, sin importar el medio (consola, terminal o aplicación de escritorio). Incluye explicaciones, respuestas, resúmenes, preguntas, mensajes de progreso, advertencias y reportes.

Esta regla no obliga a traducir nombres de clases, funciones, variables, identificadores, comandos ni rutas de archivos.

### Regla 9: Verificación

- No declarar una funcionalidad como validada sin ejecutarla. Ejecutar `python -m pytest` tras cambios en lógica, datos o rutas.
- Cambios de interfaz: verificar en el navegador contra una copia aislada del libro (por ejemplo, un directorio temporal pasado a `create_app(base_dir, config_overrides={"servidor": {"puerto": <puerto>}})`), nunca registrando datos de prueba en `data/` real.
- Cambios en la capa Excel: verificar con Python 3.10 y 3.11 cuando sea posible, y que el original conserve su SHA-256.

### Regla 10: Política de optimización de tokens

#### Objetivo

Minimizar el consumo de tokens sin afectar la calidad técnica, la arquitectura, la seguridad, la mantenibilidad, el análisis ni la calidad del código generado.

#### Reglas

1. **Eliminar verbosidad innecesaria:** sin introducciones, conclusiones ni relleno; no repetir información del contexto; respuestas directas.
2. **Maximizar la densidad de información:** lenguaje técnico conciso; listas y tablas cuando sean más eficientes.
3. **Priorizar código sobre explicaciones:** entregar primero el código; explicar solo decisiones relevantes o no evidentes.
4. **Aprovechar el contexto existente:** no volver a explicar arquitecturas o decisiones ya establecidas; referenciar componentes por nombre.
5. **Modificaciones incrementales:** devolver o editar solo las secciones modificadas; evitar regenerar archivos completos por cambios pequeños.
6. **Análisis interno, resultados externos:** entregar conclusiones, hallazgos y acciones; no exponer razonamientos intermedios innecesarios.
7. **Protección absoluta de la calidad:** nunca reducir calidad del código, arquitectura, seguridad, manejo de errores, casos límite, rendimiento, mantenibilidad, legibilidad, cobertura de pruebas, precisión técnica ni análisis de impacto.
8. **Documentación eficiente:** generar solo la documentación solicitada, sin redundancias.
9. **Análisis de código:** agrupar hallazgos, no repetir evidencia, priorizar conclusiones accionables.
10. **Conciencia de costos:** eliminar duplicaciones, ejemplos innecesarios y texto que no aporte a la solución.
11. **Código de producción:** no simplificar implementaciones importantes para reducir tokens.
12. **Balance óptimo:** prioridad 1) correctitud técnica, 2) calidad, 3) mantenibilidad, 4) eficiencia de tokens.
