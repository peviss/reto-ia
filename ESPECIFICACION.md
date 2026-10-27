# Especificación · Cuadra tus gastos

## 1. Problema y usuario

**Problema.** Cada mes o trimestre, quien tiene que justificar gastos ante una gestoría o una
junta debe emparejar a mano cada ticket o factura con su cargo en el extracto del banco, saber
cuáles faltan y sumarlos por tipo de gasto. Es lento, se pierden tickets y se descubren tarde.

**Usuario.** Personas autónomas y pequeños negocios sin conocimientos contables (por ejemplo,
una diseñadora gráfica autónoma que entrega sus gastos a la gestoría cada trimestre), y
tesoreros voluntarios de asociaciones que deben justificar los gastos de una subvención.

**Cómo se resuelve hoy sin la app.** Imprimen el extracto, buscan cada ticket en una carpeta o en
la galería del móvil, marcan con boli lo que cuadra y pasan los totales a una hoja de cálculo.
Para 30–40 movimientos al mes son 1–2 horas, y la gestoría suele devolver una lista de
"justificantes que faltan" semanas después.

**Qué resuelve la IA y qué queda fuera.**

| Lo hace la IA (Gemini, con Claude de reserva) | Lo hace Python (reglas fijas) | Queda fuera |
|---|---|---|
| Leer el extracto en cualquier formato de banco (CSV, Excel, PDF) | Emparejar ticket ↔ movimiento (mismo importe, fecha cercana) | Contabilidad oficial, IVA deducible, modelos de Hacienda |
| | Reembolsos: varios tickets ↔ un pago (combinación que suma el importe) | |
| Leer fotos de tickets y facturas PDF: comercio, fecha, total | Agrupar por categoría y sumar | Decidir si un gasto es deducible |
| Proponer una categoría para cada gasto | Detectar gastos sin comprobante y comprobantes sin gasto | Conectarse al banco (el usuario descarga el extracto) |
| | Exportar a Excel | Un ticket pagado en varios cargos (pagos fraccionados) |

**Por qué este reparto:** leer documentos variados es lo que la IA hace bien y una regla no.
Emparejar importes es lo que una regla hace bien y una IA puede inventarse: así el cruce es
comprobable y siempre da el mismo resultado.

## 2. Funcionalidades

| # | Funcionalidad | Entrada | Salida |
|---|---|---|---|
| F1 | Emparejar comprobantes con el extracto | Extracto (CSV/XLSX/PDF) + hasta 20 tickets/facturas (JPG/PNG/WEBP/HEIC/PDF) | Tabla de gastos con su comprobante (✅), varios comprobantes si es un reembolso agrupado (🔗) o "⚠️ Falta comprobante" |
| F2 | Detectar lo que falta | El mismo resultado | Lista de gastos sin justificante + lista de comprobantes que no están en el banco (efectivo, otra tarjeta, ilegibles) |
| F3 | Agrupar por categoría | El mismo resultado | Tabla y gráfico por categoría (total, nº de gastos, cuántos justificados, € sin justificar) + Excel descargable |

**Reglas de emparejamiento (en este orden):**

1. **Uno a uno:** mismo importe (±1 céntimo) y fechas a ≤ *tolerancia* días (por defecto 4). Desempate: fecha más cercana y nombre más parecido.
2. **Reembolso agrupado:** a cada gasto que siga sin comprobante (del más antiguo al más reciente) se le busca una combinación de **2 o más** comprobantes sueltos que sumen **exactamente** su importe, con fecha entre *ventana* días antes del pago (por defecto 30) y *tolerancia* días después. Cada comprobante se usa una sola vez. Si existe más de una combinación válida, se elige una y se marca **"revisar"**.
3. En la tabla, un reembolso agrupado ocupa **una fila por comprobante** con el mismo n.º de movimiento (*Mov.*), para que cada compra sume en **su** categoría.

Extras de usabilidad: botón "Probar con datos de ejemplo", ajustes de días de tolerancia (0–10, por
defecto 4) y de ventana de reembolsos (0–90, por defecto 30; 0 = no buscar), pestaña "Lo que ha leído la IA" para revisar, aviso de privacidad, y ventana para **ver cada comprobante** al pulsar sobre su nombre (en *Todos los gastos* y en *Qué falta*), con lo que ha leído la IA y el gasto del banco con el que va.

**Categorías fijas:** Alimentación · Restauración · Transporte y combustible · Suministros (luz,
agua, gas) · Telecomunicaciones y software · Material y oficina · Salud · Impuestos y cuotas ·
Compras online · Otros. Si la IA devuelve otra, se convierte en "Otros".

### 2.1 Estado de las funcionalidades

**Implementadas: 3 / 5** · Verificadas: 0 / 5 · Última actualización: 2026-10-22

| # | Funcionalidad | Estado | Dónde está | Criterios | Notas |
|---|---|---|---|---|---|
| F1 | Emparejar comprobantes con el extracto | ✅ Implementada | `cuadre.py`: `emparejar`, `agrupar_reembolsos`, `cuadrar` | CA1–CA3, CA7, CA13, CA15–CA17 | Reglas probadas en `tests/test_cuadre.py`; falta la prueba manual con la IA real |
| F2 | Detectar lo que falta | ✅ Implementada | `app.py`: pestaña «⚠️ Qué falta» | CA4, CA5, CA10 | Reglas probadas en `tests/`; falta la prueba manual con la IA real |
| F3 | Agrupar por categoría + Excel | ✅ Implementada | `cuadre.py` (agrupación), `app.py`: `a_excel`, pestaña «📊 Por categoría» | CA1, CA7 | Reglas probadas en `tests/`; falta la prueba manual con la IA real |
| F4 | Enviar los gastos a un programa de contabilidad externo | 📝 Planeada | — | — | Anunciada en HITO_SEMANA2.md; sin especificar |
| F5 | Responder preguntas sobre los gastos con un RAG | 📝 Planeada | — | — | Anunciada en HITO_SEMANA2.md; sin especificar |

Estados: 📝 Planeada · 🚧 En curso · ✅ Implementada (el código existe y se puede usar) ·
🧪 Verificada (sus criterios de aceptación pasan con los datos de ejemplo) · ❌ Descartada (no cuenta en el total).

## 3. Interfaz (Streamlit, una página)

1. Título y una frase que explica qué hace.
2. Desplegable "Cómo se usa y qué pasa con mis datos" (avisa de que los archivos van a Google y, si no responde, a Anthropic).
3. Botón **🧪 Probar con datos de ejemplo**.
4. Dos subidas de archivos en columnas: **Paso 1** extracto, **Paso 2** tickets y facturas.
5. Desplegable **Ajustes**: días de tolerancia y ventana de reembolsos.
6. Botón principal **Cuadrar gastos** con barra de progreso.
7. Resultado: 4 cifras resumen + pestañas *Por categoría*, *Todos los gastos*, *Qué falta*, *Lo que ha leído la IA* + botón **Descargar en Excel**.
8. Al pulsar sobre un comprobante en una tabla se abre una ventana con la foto o el PDF, un botón para descargarlo y, debajo, su detalle.

## 4. Pieza de IA

- **Qué usa:** Pydantic AI con un `FallbackModel`: primero Gemini (`gemini-3.8-flash`) y, si falla
  (cuota, caída, clave), Claude de Anthropic (`claude-haiku-5-5`). `temperature=0`, **salida con
  esquema** (Pydantic `Movimiento` y `Comprobante`), con lectura multimodal de imágenes y PDF.
  Basta con una de las dos claves (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`); con las dos, Claude es la reserva.
- **Por qué:** hace falta leer fotos y PDF de formatos muy distintos. Un OCR clásico saca el texto,
  pero no sabe cuál es el total ni la fecha. Gemini es multimodal, devuelve datos estructurados y
  tiene capa gratuita sin GPU. Un RAG no aplica: no hay que buscar en una base documental.
  Claude va de reserva porque la cuota gratuita de Gemini se agota pronto: así la app sigue
  funcionando. Pydantic AI permite usar los dos con el mismo código, esquemas y prompts.
- **Cómo se ahorra cuota:** las fotos se reducen a 1600 px (~300 KB); se envían 5 comprobantes por
  llamada, así que 20 comprobantes son 1 + 4 = 5 llamadas. El resultado se guarda y mover el ajuste
  de días no vuelve a llamar a la IA.
- **Qué pasa si falla:**

| Situación | Comportamiento |
|---|---|
| Falta la clave | "La app no está bien configurada (falta la clave)…" (solo si no hay ninguna de las dos) |
| Gemini falla y hay clave de Anthropic | Se repite la misma llamada con Claude, sin avisar al usuario |
| Clave no válida (400/401/403) | "La app no está bien configurada (clave no válida)…" |
| Cuota agotada (429) en el último modelo | Espera 30 s y reintenta una vez; si sigue: "Se ha agotado la cuota gratuita… espere un minuto (o vuelva mañana si persiste)" |
| Archivo dañado (400) | "La IA no ha podido abrir alguno de los archivos…" |
| Foto HEIC que no se ha podido convertir y Gemini falla | Claude no lee HEIC: mismo mensaje que el archivo dañado |
| Error del servidor (5xx) / sin red | Mensaje de probar en unos minutos |
| La IA se salta un archivo | Aparece como "No se ha podido leer" en *Qué falta* |
| La IA lee mal un importe | No cuadrará: el ticket y el gasto aparecen en *Qué falta*; el usuario lo ve en *Lo que ha leído la IA* |

## 5. Casos límite y criterios de aceptación

Datos de prueba: `ejemplos/` (inventados, regenerables con `python ejemplos/generar_ejemplos.py`).

**Pruebas automáticas** (`python -m unittest discover -s tests -v`, sin llamar a la IA): cubren
CA1–CA13 y CA15–CA18 con lo que la IA *debería* leer de los ejemplos (`tests/datos_ejemplo.py`) y
modelos de IA falsos para los errores y el paso a Claude. Quedan para la prueba manual con la app: que la IA lea
bien los ejemplos y CA14. Cada prueba lleva en su nombre el ID del criterio (`test_CA7_…`).
GitHub las pasa solas en cada push y pull request (`.github/workflows/pruebas.yml`), sin claves.

| ID | Caso | Entrada | Resultado esperado |
|---|---|---|---|
| CA1 | Caso principal | Datos de ejemplo | 10 gastos; 7 con comprobante (6 uno a uno + 1 reembolso agrupado); 1 comprobante suelto |
| CA2 | Fecha del banco posterior | Gasolinera: ticket 05/10, banco 06/10 | Emparejados (tolerancia 4 días) |
| CA3 | Mismo importe dos veces | Cafetería 12,80 € el 10/10 y el 24/10; un solo ticket del 10/10 | El ticket va con el del 10/10; el del 24/10 queda "Falta comprobante" |
| CA4 | Gastos sin comprobante | Cuota de autónomos, compra online | En *Qué falta* → gastos sin ticket |
| CA5 | Pago en efectivo | Ticket restaurante 27,40 € | En *Qué falta* → "No aparece en el extracto" |
| CA6 | Ingresos | Transferencia recibida +1.200 € | No aparece en la tabla de gastos |
| CA7 | Factura PDF | Factura de luz 68,45 € (emitida el 12/10, cargo el 14/10) | Emparejada, categoría Suministros |
| CA8 | Sin archivos | Pulsar "Cuadrar" sin nada | Aviso amarillo; no se llama a la IA |
| CA9 | Demasiados archivos | 21 comprobantes o archivo > 8 MB | Aviso con qué hacer; no se llama a la IA |
| CA10 | Foto ilegible / no es un ticket | Foto de un paisaje | Aparece como "No se ha podido leer" |
| CA11 | Sin clave | Borrar los dos secretos (`GEMINI_API_KEY` y `ANTHROPIC_API_KEY`) | Mensaje rojo; la app no se rompe |
| CA12 | Cuota agotada | 429 repetido en el último modelo | Reintento + mensaje claro; la app no se rompe |
| CA13 | Tolerancia 0 | Ajuste a 0 días con el ejemplo | Solo cuadran los gastos con la misma fecha en ticket y banco; no se llama de nuevo a la IA |
| CA15 | Reembolso agrupado | Transferencia a Marta 51,65 € (28/10) + tickets ferretería 23,45 + frutería 15,70 + copistería 12,50 | 🔗 3 filas con el mismo *Mov.*, cada una en su categoría; suman 51,65 € |
| CA16 | Reembolso ambiguo | Pago de 30 € con tickets de 10, 20, 15 y 15 € | Se agrupa una combinación y aparece el aviso «revisar» |
| CA17 | Sin búsqueda de reembolsos | Ventana = 0 con el ejemplo | La transferencia queda "Falta comprobante" y los 3 tickets como sueltos |
| CA18 | Modelo de reserva | Las dos claves; Gemini sin cuota (o clave de Gemini falsa) | Lee con Claude sin esperar ni avisar; el resultado es el mismo |
| CA14 | Usuario no técnico | Persona que no conoce la app | Con el ejemplo, entiende qué le falta en menos de 2 minutos sin ayuda |

## 6. Prompts reutilizables

### 6.1 Prompts de la app (en `app.py`)

- `PROMPT_EXTRACTO`: rol de asistente contable; devolver todos los movimientos; fecha AAAA-MM-DD;
  gastos en negativo; una categoría de la lista; no inventar ni incluir saldos.
- `PROMPT_COMPROBANTES`: un elemento por archivo con su nombre exacto; el TOTAL con IVA (no
  subtotal ni efectivo entregado); `legible=false` si hay dudas, en lugar de inventar.

La forma de la respuesta la fija el esquema (`output_type` de Pydantic AI), no el texto del prompt. Los mismos prompts sirven para Gemini y para Claude.

### 6.2 Prompt para construir o modificar la app con un agente

```
Lee AGENTS.md y ESPECIFICACION.md. Implementa <funcionalidad> respetando el reparto:
la IA solo lee documentos (app.py) y el emparejamiento es Python puro (cuadre.py).
No añadas dependencias fuera de requirements.txt. Al terminar, dime cómo comprobar
los criterios de aceptación afectados con los datos de ejemplo.
```

### 6.3 Prompt para revisar lo que ha leído la IA

```
Te paso una foto de un ticket y lo que ha extraído la app (comercio, fecha, total).
Dime si alguno de los tres datos no coincide con la foto y cuál es el valor correcto.
Si todo coincide, responde "OK".
```

### 6.4 Prompt para generar más datos de prueba

```
Añade a ejemplos/generar_ejemplos.py un ticket inventado de <tipo de comercio> con
<caso límite: total con descuento / fecha ilegible / dos IVA distintos>, y su
movimiento en el extracto si debe cuadrar. Solo datos ficticios: NIF B0000000X,
tarjeta ****4444, nombres inventados.
```

### 6.5 Skills de Claude Code (`.claude/skills/`)

Instrucciones guardadas que el agente sigue cuando la tarea encaja, para no repetir estos prompts:

| Skill | Para qué |
|---|---|
| `/features` | Llevar el estado y el conteo de las funcionalidades en §2.1 |
| `/test` | Pasar las pruebas automáticas, guiar las manuales de §5 y anotar los resultados en PRUEBA.md |
| `/commit` | Antes de cada commit: comprobar secretos, datos reales, pruebas y documentación; mensaje en español |

## 7. Dependencias

Las mismas que `requirements.txt`. Si se añade, quita o cambia un paquete, se actualiza esta tabla.

| Paquete | Para qué se usa |
|---|---|
| `streamlit>=1.38` | Interfaz web y despliegue en Streamlit Community Cloud |
| `pydantic-ai-slim[google,anthropic]>=2.60,<3` | Llamadas a la IA (lectura de extractos y comprobantes): Gemini y, de reserva, Claude (Anthropic). Instala `google-genai` y `anthropic` |
| `pandas` | Tablas de gastos y agrupación por categoría; pasar el extracto Excel a texto antes de enviarlo a la IA |
| `openpyxl` | Leer el extracto Excel y escribir el Excel descargable |
| `pillow` | Reducir las fotos a 1600 px antes de enviarlas a la IA |
