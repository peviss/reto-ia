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
| Entender las preguntas del usuario sobre su cuadre y responderlas en lenguaje sencillo | Filtrar y sumar los gastos que pide la pregunta | Preguntas sobre varios cuadres a la vez; consejos fiscales |

**Por qué este reparto:** leer documentos variados es lo que la IA hace bien y una regla no.
Emparejar importes es lo que una regla hace bien y una IA puede inventarse: así el cruce es
comprobable y siempre da el mismo resultado.

## 2. Funcionalidades

| # | Funcionalidad | Entrada | Salida |
|---|---|---|---|
| F1 | Emparejar comprobantes con el extracto | Extracto (CSV/XLSX/PDF) + hasta 20 tickets/facturas (JPG/PNG/WEBP/HEIC/PDF) | Tabla de gastos con su comprobante (✅), varios comprobantes si es un reembolso agrupado (🔗) o "⚠️ Falta comprobante" |
| F2 | Detectar lo que falta | El mismo resultado | Lista de gastos sin justificante + lista de comprobantes que no están en el banco (efectivo, otra tarjeta, ilegibles) |
| F3 | Agrupar por categoría | El mismo resultado | Tabla y gráfico por categoría (total, nº de gastos, cuántos justificados, € sin justificar) + Excel descargable |
| F5 | Conversar con lo extraído | Preguntas en lenguaje natural sobre el cuadre abierto («¿cuánto gasté en restauración?», «¿qué compré en la ferretería?») | Respuesta breve; si lleva un total, lo calcula Python y se muestran los gastos sumados |

**Reglas de emparejamiento (en este orden):**

1. **Uno a uno:** mismo importe (±1 céntimo) y fechas a ≤ *tolerancia* días (por defecto 4). Desempate: fecha más cercana y nombre más parecido.
2. **Reembolso agrupado:** a cada gasto que siga sin comprobante (del más antiguo al más reciente) se le busca una combinación de **2 o más** comprobantes sueltos que sumen **exactamente** su importe, con fecha entre *ventana* días antes del pago (por defecto 30) y *tolerancia* días después. Cada comprobante se usa una sola vez. Si existe más de una combinación válida, se elige una y se marca **"revisar"**.
3. En la tabla, un reembolso agrupado ocupa **una fila por comprobante** con el mismo n.º de movimiento (*Mov.*), para que cada compra sume en **su** categoría.

Extras de usabilidad: botón "Probar con datos de ejemplo", ajustes de días de tolerancia (0–10, por
defecto 4) y de ventana de reembolsos (0–90, por defecto 30; 0 = no buscar), pestaña "Lo que ha leído la IA" para revisar, aviso de privacidad, y ventana para **ver cada comprobante** al pulsar sobre su nombre (en *Todos los gastos* y en *Qué falta*), con lo que ha leído la IA y el gasto del banco con el que va.

**Memoria en el navegador (IndexedDB, `almacen.py`):** lo que lee la IA se guarda en el navegador de quien usa la app, identificado por la huella (SHA-256) del contenido de cada archivo. Si se vuelve a subir un archivo ya leído (aunque cambie de nombre), se usa lo guardado y **no se llama a la IA**. También se guarda cada **cuadre** (extracto + comprobantes leídos) en un historial (F6) y los **archivos de los comprobantes** (fotos reducidas a ~300 KB, PDF tal cual) para verlos al abrir un cuadre. Los archivos viajan una vez en base64 hasta el navegador, se guardan como `Blob` (una sola vez aunque estén en varios cuadres) y **no vuelven al servidor**: los muestra un componente que los lee de IndexedDB. Al eliminar un cuadre o sustituir un ticket se borran los archivos que ya no usa ningún cuadre. Las lecturas ilegibles no se guardan (para que la IA lo intente de nuevo) y nada pasa por un servidor propio. Si cambian los prompts o los esquemas, se sube `VERSION_LECTURA` y lo leído antes deja de usarse. Se puede borrar en *Ajustes*.

**Categorías fijas:** Alimentación · Restauración · Transporte y combustible · Suministros (luz,
agua, gas) · Telecomunicaciones y software · Material y oficina · Salud · Impuestos y cuotas ·
Compras online · Otros. Si la IA devuelve otra, se convierte en "Otros".

### 2.1 Estado de las funcionalidades

**Implementadas: 5 / 6** · Verificadas: 0 / 6 · Última actualización: 2026-10-27

| # | Funcionalidad | Estado | Dónde está | Criterios | Notas |
|---|---|---|---|---|---|
| F1 | Emparejar comprobantes con el extracto | ✅ Implementada | `cuadre.py`: `emparejar`, `agrupar_reembolsos`, `cuadrar` | CA1–CA3, CA7, CA13, CA15–CA17 | Reglas probadas en `tests/test_cuadre.py`; falta la prueba manual con la IA real |
| F2 | Detectar lo que falta | ✅ Implementada | `app.py`: pestaña «⚠️ Qué falta» | CA4, CA5, CA10 | Reglas probadas en `tests/`; falta la prueba manual con la IA real |
| F3 | Agrupar por categoría + Excel | ✅ Implementada | `cuadre.py` (agrupación), `app.py`: `a_excel`, pestaña «📊 Por categoría» | CA1, CA7 | Reglas probadas en `tests/`; falta la prueba manual con la IA real |
| F6 | Historial de cuadres: abrir, ampliar con más comprobantes, renombrar, eliminar y empezar uno nuevo | ✅ Implementada | `almacen.py` (IndexedDB); `app.py`: barra lateral «Mis cuadres», `empezar`, `juntar_comprobantes` | CA19–CA22 | Probado en Chrome con los ejemplos (sin llamar a la IA) y en `tests/test_app.py` |
| F4 | Enviar los gastos a un programa de contabilidad externo | 📝 Planeada | — | — | Anunciada en HITO_SEMANA2.md; sin especificar |
| F5 | Conversar con lo extraído (RAG) | ✅ Implementada | `cuadre.py`: `consultar_gastos`; `app.py`: `datos_para_conversar`, `conversar`, pestaña «💬 Pregunte» | CA23–CA25 | Reglas y conversación con modelo falso probadas en `tests/`; falta la prueba manual con la IA real |

Estados: 📝 Planeada · 🚧 En curso · ✅ Implementada (el código existe y se puede usar) ·
🧪 Verificada (sus criterios de aceptación pasan con los datos de ejemplo) · ❌ Descartada (no cuenta en el total).

## 3. Interfaz (Streamlit, una página)

0. **Barra lateral «🗂️ Mis cuadres»:** botón **➕ Nuevo cuadre** (página vacía) y la lista de cuadres guardados en el navegador, del más reciente al más antiguo, con su fecha y n.º de comprobantes. Al pulsar uno se abre.
1. Título y una frase que explica qué hace.
2. Desplegable "Cómo se usa y qué pasa con mis datos" (avisa de que los archivos van a Google y, si no responde, a Anthropic, y de que lo leído se guarda solo en este navegador).
   Debajo, el cuadre abierto (📂 nombre, extracto, n.º de comprobantes), un campo para **cambiarle el nombre** y **🗑️ Eliminar este cuadre**; o «Nuevo cuadre».
3. Botón **🧪 Probar con datos de ejemplo** (empieza un cuadre nuevo).
4. Dos subidas de archivos en columnas: **Paso 1** extracto, **Paso 2** tickets y facturas. Con un cuadre abierto, el extracto es opcional (solo para cambiarlo) y el paso 2 es «Más tickets y facturas»; tras guardar, las subidas se vacían.
5. Desplegable **Ajustes**: días de tolerancia, ventana de reembolsos y botón **🗑️ Borrar lo guardado en este navegador**.
6. Botón principal **Cuadrar gastos** (cuadre nuevo) o **Añadir al cuadre** (cuadre abierto: suma los comprobantes nuevos a los que tenía; si uno se llama igual, manda el nuevo) con barra de progreso. El resultado se guarda en el historial.
7. Resultado: 4 cifras resumen + pestañas *Por categoría*, *Todos los gastos*, *Qué falta*, *Lo que ha leído la IA*, *Pregunte* + botón **Descargar en Excel**.
   En **💬 Pregunte**, un chat sobre el cuadre abierto (preguntas y respuestas en un recuadro con desplazamiento y el campo para escribir siempre debajo): cada respuesta con un total lleva un desplegable con los gastos que ha sumado la app. Botón **🗑️ Borrar la conversación**; al abrir otro cuadre, añadirle comprobantes o empezar uno nuevo, la conversación empieza de cero (no se guarda en el navegador).
8. Al pulsar sobre un comprobante en una tabla se abre una ventana con la foto o el PDF, un botón para descargarlo y, debajo, su detalle. Si el cuadre se abrió del historial, el archivo sale de IndexedDB.

## 4. Pieza de IA

- **Qué usa:** Pydantic AI con un `FallbackModel`: primero Gemini (`gemini-3.8-flash`) y, si falla
  (cuota, caída, clave), Claude de Anthropic (`claude-haiku-5-5`). `temperature=0`, **salida con
  esquema** (Pydantic `Movimiento` y `Comprobante`), con lectura multimodal de imágenes y PDF.
  Basta con una de las dos claves (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`); con las dos, Claude es la reserva.
- **Por qué:** hace falta leer fotos y PDF de formatos muy distintos. Un OCR clásico saca el texto,
  pero no sabe cuál es el total ni la fecha. Gemini es multimodal, devuelve datos estructurados y
  tiene capa gratuita sin GPU.
  Claude va de reserva porque la cuota gratuita de Gemini se agota pronto: así la app sigue
  funcionando. Pydantic AI permite usar los dos con el mismo código, esquemas y prompts.
- **Conversación (F5), un RAG sin base vectorial:** la *recuperación* la hace Python. Un cuadre tiene como
  mucho unos cientos de filas, así que **todo lo extraído** (gastos con su comprobante, comprobantes sueltos,
  lo leído de cada comprobante e ingresos) va en CSV en las instrucciones (`datos_para_conversar`). Para
  totales y recuentos la IA llama a la herramienta `sumar_gastos` (filtros: categoría, fechas, texto, con o sin
  justificante), que ejecuta `consultar_gastos` en `cuadre.py`: así la IA entiende y redacta, pero **no suma**.
  No se usa una base vectorial (Chroma o similar) porque buscar «trozos parecidos» puede dejarse filas al sumar,
  los datos tendrían que guardarse en el servidor (y deben quedarse en el navegador) y añadiría una dependencia pesada.
  Se le recuerdan a la IA las últimas 10 preguntas (`TURNOS_RECORDADOS`).
- **Cómo se ahorra cuota:** las fotos se reducen a 1600 px (~300 KB); se envían 5 comprobantes por
  llamada, así que 20 comprobantes son 1 + 4 = 5 llamadas. El resultado se guarda y mover el ajuste
  de días no vuelve a llamar a la IA. Lo leído se guarda en el navegador (IndexedDB): volver a subir los mismos
  archivos, aunque sea otro día, no gasta cuota.
  Cada pregunta de la conversación suele costar 2 llamadas (pedir la suma y redactar).
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
| Falla la IA en la conversación | Los mismos mensajes que arriba (con un reintento si es 429); la pregunta no se guarda y se puede repetir |

## 5. Casos límite y criterios de aceptación

Datos de prueba: `ejemplos/` (inventados, regenerables con `python ejemplos/generar_ejemplos.py`).

**Pruebas automáticas** (`python -m unittest discover -s tests -v`, sin llamar a la IA): cubren
CA1–CA13, CA15–CA22, CA23 y CA24 con lo que la IA *debería* leer de los ejemplos (`tests/datos_ejemplo.py`) y
modelos de IA falsos para los errores y el paso a Claude. Quedan para la prueba manual con la app: que la IA lea
bien los ejemplos, CA14, CA25 y que las respuestas de la conversación sean correctas con la IA real. Cada prueba lleva en su nombre el ID del criterio (`test_CA7_…`).
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
| CA19 | Archivos ya leídos | Cuadrar el ejemplo dos veces (o cambiar el nombre de un ticket y volver a subirlo) | La segunda vez no se llama a la IA para esos archivos; mismo resultado |
| CA20 | Historial | Cuadrar el ejemplo, recargar la página y abrirlo en *Mis cuadres* | Aparece con su fecha; al abrirlo, el mismo resultado sin llamar a la IA. *Nuevo cuadre* deja la página vacía |
| CA22 | Ver los archivos de un cuadre guardado | Cuadrar el ejemplo, recargar la página, abrir el cuadre y pulsar un ticket y un PDF | Se ven la foto y el PDF con su botón de descarga; al eliminar el cuadre se borran sus archivos (si ningún otro cuadre los usa) |
| CA21 | Ampliar un cuadre | Cuadre con extracto + 3 tickets; abrirlo y subir 2 tickets más → «Añadir al cuadre» | El cuadre tiene 5 comprobantes y se recalcula; el extracto se mantiene; sin archivos nuevos → aviso |
| CA23 | Pregunta con un total | Ejemplo → *Pregunte*: «¿Cuánto he gastado en restauración?» | 25,60 € (2 gastos), igual que en *Por categoría*; el desplegable muestra las 2 filas |
| CA24 | Conversación seguida | Tras CA23: «¿Y cuáles no tienen ticket?» | Entiende la pregunta anterior; abrir otro cuadre o *Nuevo cuadre* vacía la conversación. Sin clave: mensaje rojo |
| CA25 | Pregunta sin respuesta en los datos | «¿Cuánto gasté en enero?» o «¿Es deducible la gasolina?» | Dice que no está en el cuadre o que no puede aconsejar; no inventa importes |
| CA14 | Usuario no técnico | Persona que no conoce la app | Con el ejemplo, entiende qué le falta en menos de 2 minutos sin ayuda |

## 6. Prompts reutilizables

### 6.1 Prompts de la app (en `app.py`)

- `PROMPT_EXTRACTO`: rol de asistente contable; devolver todos los movimientos; fecha AAAA-MM-DD;
  gastos en negativo; una categoría de la lista; no inventar ni incluir saldos.
- `PROMPT_COMPROBANTES`: un elemento por archivo con su nombre exacto; el TOTAL con IVA (no
  subtotal ni efectivo entregado); `legible=false` si hay dudas, en lugar de inventar.

- `PROMPT_CONVERSACION` (F5): responder solo con los datos del cuadre (van debajo, en CSV); para totales y
  recuentos usar **siempre** la herramienta `sumar_gastos`; un reembolso agrupado es un solo pago; si no está en
  los datos, decirlo; sin consejos fiscales; de usted, breve, importes con coma y «€».

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
