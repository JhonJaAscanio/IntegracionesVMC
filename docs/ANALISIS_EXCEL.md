# Análisis del libro `WPOSS_Checklist_Pruebas_Vending_5320.xlsx`

Inspección realizada con `openpyxl` y lectura directa del XML del `.xlsx` (Fase 1).

## 1. Hojas

| # | Hoja | Rango | Contenido |
|---|------|-------|-----------|
| 1 | Instrucciones | A1:A38 | Guía de uso, leyenda de colores, reglas de diligenciamiento, alcance y preguntas abiertas. Sin fórmulas. |
| 2 | Listas (oculta) | A1:G8 | Catálogos de las listas desplegables. |
| 3 | Identificación y Versiones | A1:Z29 | Una fila por sesión (26 columnas). Paneles fijos en K2. |
| 4 | Revisión Física y Eléctrica | A1:E33 | 8 ítems de inspección por sesión. |
| 5 | Casos de Prueba | A1:O46 | Casos por componente (15 columnas). |
| 6 | Incidencias | A1:O29 | Hallazgos (15 columnas). |
| 7 | Cierre de Sesión | A1:AD19 | Resumen por sesión con fórmulas; columnas C:R agrupadas (outline). |

### Catálogos (hoja Listas)

| Columna | Catálogo | Valores |
|---|---|---|
| A | Estados | Aprobado, Fallido, Bloqueado, Pendiente, No aplica, En observación |
| B | Severidad | Crítica, Alta, Media, Baja |
| C | Tipo de verificación | Prueba ejecutada, Revisión documental |
| D | Componente | Máquina Vending, POS NEW5320, MDB, Financiera, Agente Polaris, Operación / Dispensación, Otro |
| E | Tipo de prueba (sesión) | Instalación, Diagnóstico, Compatibilidad, Piloto, Actualización de versión, Regresión, Otro |
| F | Estado de incidencia | Abierto, En progreso, Pendiente de reprueba, Cerrado |
| G | Concepto final | Apto para piloto, Apto con condiciones, No apto, Pendiente |

### Listas desplegables (validaciones)

Todas son validaciones de **extensión x14** que apuntan a la hoja Listas:

| Hoja | Rango | Origen |
|---|---|---|
| Identificación y Versiones | M2:M30 (Tipo de prueba) | Listas!E2:E8 |
| Revisión Física y Eléctrica | C2:C34 (Resultado) | Listas!A2:A7 |
| Casos de Prueba | C2:C47 / D2:D47 / J2:J47 | Listas!D / C / A |
| Incidencias | I2:I30 (Severidad) / N2:N30 (Estado) | Listas!B / F |
| Cierre de Sesión | AB2:AB20 (Concepto final) | Listas!G2:G5 |

No hay formato condicional, nombres definidos ni tablas de Excel.

## 2. Relaciones

Todas las hojas se enlazan por **`Sesión ID`** (formato `SES-001`):

```
Identificación y Versiones (1 fila por sesión)
 ├── Revisión Física y Eléctrica   (N ítems por sesión)       col A
 ├── Casos de Prueba               (N pruebas por sesión)     col B
 │     └── Incidencia asociada (col N) ──► Incidencias.ID
 ├── Incidencias                   (N por sesión)             col C
 └── Cierre de Sesión              (1 fila por sesión)        col A
```

La relación prueba → incidencia existe solo en un sentido (Casos de Prueba!N). El libro no
tiene en Incidencias una columna con la prueba de origen.

## 3. Fórmulas (hoja Cierre de Sesión, filas 2 a 19)

| Columnas | Fórmula | Equivalente en la app |
|---|---|---|
| C:R | `INDEX/MATCH` sobre Identificación y Versiones por Sesión ID (fecha, cliente, fabricante, modelo, seriales, firmware, MDB×3, Financiera, Polaris, participantes, responsable, objetivo) | Lectura directa de la sesión |
| S Total planificadas | `COUNTIF(Casos!B2:B1000, A)` | Nº de pruebas de la sesión |
| T Total ejecutadas | `COUNTIFS(B=A, J<>"Pendiente", J<>"")` | Pruebas con estado distinto de Pendiente y de vacío (**incluye "No aplica" y "En observación"**, igual que la fórmula) |
| U/V/W/X | `COUNTIFS(B=A, J="Aprobado"/"Fallido"/"Bloqueado"/"Pendiente")` | Conteo por estado |
| Y Incidencias abiertas | `COUNTIFS(C=A, N<>"Cerrado") - COUNTIFS(C=A, N="")` | Incidencias con estado no vacío y distinto de Cerrado |
| AD Resumen para correo | Concatenación con `CHAR(10)` | `Service.email_summary()` reproduce el mismo texto |

Columnas de captura manual: A (Sesión ID), B (Fecha de cierre), Z (Versiones y equipos
cubiertos), AA (Pendientes), AB (Concepto final), AC (Responsable del cierre).

**openpyxl no recalcula fórmulas.** La aplicación calcula todos los totales en Python y
conserva las fórmulas en el libro; al guardar se marca `fullCalcOnLoad` para que Excel las
recalcule al abrirlo. Las filas de cierre nuevas reciben exactamente las mismas fórmulas.

## 4. Registros existentes

| Sesión | Situación |
|---|---|
| SES-001 | **Ejemplo**: Observaciones = "Fila de ejemplo — reemplazar…"; todos los datos "Pendiente de confirmar". |
| SES-002 | Datos reales de un cliente piloto (FW 13.0.13). En Revisión y Casos conserva el texto de plantilla "Fila de ejemplo — duplicar…" en Observaciones aunque los resultados son reales. |
| SES-003 | Datos reales de un cliente piloto (FW 13.0.22). Faltan Modelo y Serial de máquina. Responsable con salto de línea. Hora guardada como hora de Excel (no texto). |
| INC-001..003 | **Ejemplo**: Descripción "Fila de ejemplo — reemplazar…", estado Abierto. |

Datos incompletos o heterogéneos detectados: Serial POS guardado como número en SES-002,
fechas guardadas como texto `AAAA-MM-DD`, valores "Estándar" en campos de versión MDB.

## 5. Riesgos y decisiones

| Riesgo | Decisión |
|---|---|
| openpyxl **elimina las validaciones x14** al guardar | Se regeneran en cada guardado como validaciones estándar equivalentes, apuntando a Listas y con el rango ampliado a la fila 2000. |
| Las fórmulas del cierre cuentan las incidencias de ejemplo (INC-002/003 Abiertas) | La app excluye por defecto los registros marcados "Fila de ejemplo" (configurable) e indica en pantalla cuándo Excel mostrará un número distinto. No se borra nada automáticamente; existe la acción explícita "Eliminar fila de ejemplo", que deja el contenido en el historial. |
| Rangos fijos `$2:$1000` en las fórmulas | Suficiente para ~10 sesiones/mes durante años; documentado como límite. |
| El libro no tiene País/Ciudad, estado de borrador, prueba asociada en Incidencias, ni metadatos de evidencias/historial | Se agregan columnas **al final** de las hojas (no se insertan, para no desplazar referencias) y hojas `App_Sesiones`, `App_Evidencias`, `App_Historial`, `App_Contadores`. |
| Catálogos de País, Fabricante e Ítems de revisión no existen | Se agregan columnas H, I, J a Listas. Ítems = los 8 del libro; Fabricantes = los ya registrados; Países = lista inicial ampliable. |
| Criterios de "Apto para piloto" no definidos (pregunta abierta en Instrucciones A38) | Configuración explícita en `config.json` → `cierre`. Valores por defecto conservadores; la componente crítica queda vacía hasta que WPOSS la confirme. |
| Numeración de pruebas del libro = número de sesión (POS-002 para SES-002) | No es única con varias pruebas por componente. La app usa numeración secuencial global por prefijo (MDB-004, MDB-005…) y un contador que nunca reutiliza números. |
| Texto que empieza con `=` se guardaría como fórmula | Se fuerza el tipo texto en todas las escrituras. |
| Libro abierto en Excel | Se detecta (archivo `~$` o bloqueo del sistema). El cambio no se declara guardado; queda en `data/pendientes/` y se aplica al reintentar. |
