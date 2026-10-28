# WPOSS Vending Integration Manager

Aplicación web local para registrar, consultar y cerrar las visitas técnicas de integración
de máquinas vending con el POS NEW5320. Usa como almacenamiento un libro Excel `.xlsx` local
basado en `WPOSS_Checklist_Pruebas_Vending_5320.xlsx`. Funciona sin internet, sin servicios
en la nube y sin necesidad de tener Excel instalado.

## 1. Requisitos

- Windows 10/11.
- Python 3.10 o superior ([python.org](https://www.python.org/downloads/)); probado con 3.10 y 3.11.
  Al instalar, marque **"Add python.exe to PATH"**.
- Chrome o Edge.
- Internet **solo la primera vez**, para descargar las dependencias.

## 2. Iniciar la aplicación

> **El libro Excel no está en el repositorio** porque contiene datos de clientes. Después de
> clonar, copie `WPOSS_Checklist_Pruebas_Vending_5320.xlsx` en la carpeta raíz del proyecto
> (junto a `app.py`). Sin ese archivo la aplicación no inicia.

**Forma recomendada: `abrir_plataforma.bat`**

1. Haga doble clic en **`abrir_plataforma.bat`** (puede crear un acceso directo en el escritorio).
2. La primera vez se crea el entorno `.venv` y se instalan las dependencias (1–2 minutos).
3. El servidor se inicia en una ventana minimizada llamada *"WPOSS servidor"* y, cuando
   responde, se abre el navegador en **http://127.0.0.1:5000**.
4. Si la plataforma ya estaba en ejecución, solo abre el navegador (no inicia un segundo servidor).
5. Para detener la plataforma, cierre la ventana minimizada *"WPOSS servidor"*.

El puerto se toma de `config.json` → `servidor.puerto`.

**Alternativa: `iniciar.bat`** inicia el servidor en la ventana visible y abre el navegador;
para detenerlo, cierre esa ventana.

Desde una terminal también puede ejecutarse con:

```bash
python app.py
```

La aplicación escucha solo en `127.0.0.1`: no es accesible desde otros equipos de la red.

## 3. Archivos y carpetas

```
Integraciones VMC/
├── WPOSS_Checklist_Pruebas_Vending_5320.xlsx   Libro original (NUNCA se modifica; no versionado)
├── app.py                 Punto de entrada
├── abrir_plataforma.bat   Inicia el servidor minimizado (si no está activo) y abre el navegador
├── iniciar.bat            Inicio en Windows con la consola visible
├── config.json            Configuración local (se crea en el primer inicio)
├── requirements.txt
├── wposs_vim/             Código de la aplicación
│   ├── __init__.py        Creación de la app
│   ├── routes.py          Rutas web
│   ├── services.py        Lógica de negocio (cierre, totales, filtros)
│   ├── excel_store.py     Capa única de acceso al Excel (lectura, escritura segura, diario)
│   ├── operations.py      Operaciones de escritura sobre el libro
│   ├── schema.py          Hojas, columnas y catálogos
│   ├── validators.py      Validaciones
│   ├── evidence.py        Evidencias
│   ├── backups.py         Respaldos y restauración
│   ├── reports.py         Exportación a Excel
│   ├── security.py        Acceso local, CSRF, logs
│   ├── templates/  static/
├── data/
│   ├── original/          Copia íntegra del original + ORIGEN.txt con su SHA-256
│   ├── trabajo/           WPOSS_Vending_Datos.xlsx  ← libro de trabajo (datos reales)
│   ├── evidencias/SES-xxx/  Archivos adjuntos por sesión
│   ├── pendientes/        Cambios que no pudieron escribirse (Excel abierto)
│   └── exportaciones/     Exportaciones generadas
├── respaldos/             Copias de seguridad con fecha y hora
├── logs/app.log           Registro de operaciones y errores
├── docs/ANALISIS_EXCEL.md Estructura del libro, fórmulas, relaciones y riesgos
└── tests/                 Pruebas automatizadas (pytest) y libro anonimizado en tests/fixtures/
```

En el primer inicio se copia el libro original a `data/trabajo/WPOSS_Vending_Datos.xlsx` y se
le agregan, sin modificar las celdas existentes:

- Columnas **País** y **Ciudad** al final de *Identificación y Versiones*.
- Columna **ID de prueba asociada** al final de *Incidencias*.
- Catálogos **País**, **Fabricante máquina** e **Ítem de revisión física** en *Listas*.
- Hojas **App_Sesiones** (borrador/en curso/cerrada), **App_Evidencias** (rutas y metadatos),
  **App_Historial** (cambios campo a campo) y **App_Contadores** (IDs emitidos).

Las hojas originales, sus fórmulas, formatos y la hoja *Instrucciones* se conservan.

## 4. Uso

| Sección | Para qué sirve |
|---|---|
| Dashboard | Indicadores calculados desde el libro, con filtros por fecha, cliente, fabricante, modelo, firmware y estado. Sin datos muestra un estado vacío, nunca cifras ficticias. |
| Visitas e integraciones | Histórico con búsqueda, filtros, orden y paginación. Cada fila abre la ficha de la sesión. |
| Nueva visita | Formulario en 4 pasos. **Guardar borrador** permite completarlo después. El Sesión ID se asigna solo. El botón **Pendiente** escribe "Pendiente de confirmar". |
| Ficha de la sesión | Pestañas Resumen, Revisión física, Pruebas, Incidencias, Evidencias e Historial. |
| Revisión física y eléctrica | Crea los 8 ítems del checklist por sesión; permite ítems adicionales. |
| Casos de prueba | El ID se genera según el componente (MDB-004…). Una prueba **nunca** se aprueba sola: Aprobado/Fallido exigen resultado obtenido, y cambiar de Pendiente exige resultado esperado. |
| Incidencias | Desde una prueba Fallida o Bloqueada, **Crear incidencia** precarga sesión, componente, versión y resultados. Cada cambio de estado queda en el historial. Editar una prueba no cierra sus incidencias. |
| Cierre de sesión | Totales equivalentes a las fórmulas del libro, criterios de aceptación, concepto sugerido (orientativo), pendientes por responsable y **resumen para correo** con botón Copiar. |
| Reportes | Exportar a Excel (libro nuevo), comparar 2–6 sesiones, pruebas por serial de POS e historial de un modelo. El **informe** de cada sesión se imprime o guarda como PDF desde el navegador. |
| Configuración y respaldos | Catálogos, criterios de cierre, retención de respaldos, restauración, cambios pendientes y log. |

### Criterios de cierre

El libro original no define cuándo una combinación es apta para piloto (pregunta abierta en
*Instrucciones*). Por eso los criterios son configurables (`config.json` → `cierre`, o en
Configuración). Por defecto, **"Apto para piloto"** solo se permite si hay al menos una prueba
ejecutada y no hay pruebas fallidas, bloqueadas o pendientes, ni incidencias abiertas, y la
revisión física está completa sin fallos. **"Apto con condiciones"** exige documentar los
pendientes. Se pueden declarar **componentes críticos** que deben tener al menos una prueba
aprobada (por defecto ninguno, hasta que WPOSS lo confirme).

### Filas de ejemplo

El libro original trae filas de ejemplo (SES-001 y las incidencias INC-001..003). Se
identifican por el texto "Fila de ejemplo" y, por defecto, se excluyen de indicadores y totales.
No se borran automáticamente. En la ficha, las incidencias de ejemplo tienen un botón para
eliminarlas tras confirmación (su contenido queda en *App_Historial*). Mientras existan, las
fórmulas de Excel del cierre las siguen contando; la pantalla de cierre avisa la diferencia.

## 5. Si el Excel está abierto

Puede abrir `data/trabajo/WPOSS_Vending_Datos.xlsx` en Excel para consultarlo, pero **ciérrelo
antes de registrar datos en la aplicación**. Si el libro está abierto:

- La aplicación muestra *"El cambio NO se guardó en el libro"*.
- El cambio queda en `data/pendientes/` (no se pierde al cerrar el navegador ni al reiniciar).
- Un aviso amarillo indica cuántos cambios están pendientes. Cierre Excel y pulse **Reintentar**.
  También se reintentan al iniciar la aplicación y antes de la siguiente escritura.

No edite el libro de trabajo en Excel mientras la aplicación tenga cambios pendientes.

## 6. Evidencias

- Se guardan en `data/evidencias/<Sesión ID>/`; el libro solo guarda la **ruta relativa**
  (columna *Evidencia* del registro y hoja *App_Evidencias* con tamaño, SHA-256 y fecha).
- Extensiones permitidas y tamaño máximo (25 MB) en `config.json` → `evidencias`.
- Los nombres se normalizan y nunca se sobrescribe un archivo existente (`foto.jpg`, `foto-1.jpg`…).
- En archivos de texto/log se buscan secuencias con formato de número de tarjeta y se muestra una
  advertencia. **Revise y redacte los logs de transacciones antes de adjuntarlos**: no adjunte
  credenciales, claves ni números completos de tarjetas.

## 7. Respaldos y restauración

- **Automáticos**: antes de escribir, si el último tiene más de 60 minutos (configurable).
  Se conservan los últimos 30 (configurable).
- **Manuales**: botón *Crear respaldo ahora*. No se eliminan por retención.
- Ubicación: `respaldos/auto_AAAAMMDD_HHMMSS.xlsx`, `manual_…`, `previo_restauracion_…`.

**Restaurar un respaldo**

1. Cierre el libro de trabajo si está abierto en Excel.
2. Vaya a *Configuración y respaldos* → *Respaldos* y pulse **Restaurar** en el archivo deseado.
3. La aplicación valida el archivo (hojas y columnas obligatorias, sin Sesión ID duplicados),
   guarda el estado actual como `previo_restauracion_…` y reemplaza el libro de trabajo.
4. Si se equivocó, restaure el respaldo `previo_restauracion_…`.

Restauración manual (con la aplicación detenida): copie el respaldo elegido sobre
`data/trabajo/WPOSS_Vending_Datos.xlsx`.

Los respaldos cubren el libro. Copie también la carpeta `data/evidencias/` para conservar los adjuntos.

## 8. Pruebas automatizadas

```bash
python -m pytest
```

Las pruebas trabajan sobre copias temporales de `tests/fixtures/checklist_anonimizado.xlsx`, una
versión del libro WPOSS con la misma estructura y fórmulas pero con clientes, personas y seriales
ficticios. No necesitan el libro original y no tocan `data/`.

## 9. Seguridad

- Servidor ligado a `127.0.0.1`; se rechazan peticiones de otras direcciones y cabeceras Host no locales.
- Token CSRF en todos los formularios; clave de sesión generada en el equipo (`data/.secret_key`).
- Rutas de evidencias y respaldos restringidas a sus carpetas.
- Los logs enmascaran secuencias con formato de número de tarjeta.

## 10. Problemas conocidos y límites

- Las fórmulas del cierre del libro original cubren las filas 2–1000 de *Casos de Prueba* e *Incidencias*.
- Las fórmulas de Excel incluyen las filas de ejemplo; los totales de la app las excluyen (configurable).
- La columna *Ejecutadas* sigue la fórmula original: cuenta "No aplica" y "En observación" como ejecutadas.
- El informe PDF se genera con *Imprimir → Guardar como PDF* del navegador.
- Un único usuario/equipo. No abra la aplicación en dos equipos sobre el mismo archivo compartido.
