# 🧾 Cuadra tus gastos

**Tus tickets y tu extracto del banco, cuadrados en un minuto.**
Sube el extracto y las fotos de tus tickets o facturas. La app te dice qué gasto corresponde a
cada justificante, qué te falta y cuánto has gastado por categoría, listo para la gestoría.

- **App:** [https://reto-ia-peviss.streamlit.app](https://reto-ia-peviss.streamlit.app)
- **Repositorio:** https://github.com/peviss/reto-ia

## Pitch

1. **Problema:** Quien lleva la contabilidad de una pequeña empresa o controla sus propios gastos pasa 1–2 horas al mes emparejando a mano tickets y facturas con el extracto del banco, y descubre tarde los justificantes que faltan.
2. **Solución:** Cuadra tus gastos lee el extracto y las fotos de los tickets, empareja cada gasto con su justificante (también los reembolsos que juntan varios tickets), lista lo que falta y lo agrupa por categoría en un Excel.
3. **Qué aporta la IA:** Gemini lee tickets arrugados, facturas PDF y extractos de cualquier banco sin plantillas, y el cruce lo hacen reglas fijas para que el resultado sea comprobable.
4. **Lo que aprendimos de la prueba:** Una documento de especificacion bien redactado y completo es clave para el desarrollo de una app de
5. **Siguiente paso:** Conectar la API KEY de Gemini e implementar las funcionalidades 2 y 3.

## Especificación

La especificación completa está en [ESPECIFICACION.md](ESPECIFICACION.md). Resumen:

| # | Funcionalidad | Entrada | Salida |
|---|---|---|---|
| F1 | Emparejar comprobantes con el extracto | Extracto (CSV/XLSX/PDF) + hasta 20 tickets o facturas (JPG/PNG/WEBP/HEIC/PDF), opcionales | Cada gasto con su comprobante (✅), varios comprobantes si es un reembolso (🔗) o «⚠️ Falta comprobante» |
| F2 | Detectar lo que falta | El resultado de F1 | Gastos sin justificante + comprobantes que no están en el banco (efectivo, otra tarjeta, ilegibles) |
| F3 | Agrupar por categoría | El resultado de F1 | Tabla y gráfico por categoría + Excel descargable |

**Criterios de aceptación (selección, con casos límite):**

| ID | Caso | Resultado esperado |
|---|---|---|
| CA1 | Datos de ejemplo | 10 gastos; 7 con comprobante (6 uno a uno + 1 reembolso de 3 tickets); 1 comprobante suelto |
| CA2 | Ticket del 05/10 cobrado el 06/10 | Emparejados (tolerancia de 4 días) |
| CA3 | Mismo importe dos veces y un solo ticket | El ticket va con el gasto de fecha más cercana; el otro queda «Falta comprobante» |
| CA5 | Ticket pagado en efectivo | Aparece en *Qué falta* → «No aparece en el extracto» |
| CA8 | Pulsar «Cuadrar» sin archivos | Aviso; no se llama a la IA |
| CA10 | Foto que no es un ticket | Aparece como «No se ha podido leer» |
| CA12 | Cuota agotada en Gemini y en Claude | Un reintento y mensaje claro; la app no se rompe |
| CA18 | Cuota de Gemini agotada, con clave de Anthropic | Lee con Claude sin esperar; mismo resultado |
| CA16 | Reembolso con varias combinaciones posibles | Se agrupa una y aparece el aviso «revisar» |
| CA19 | Volver a subir archivos ya leídos | No se llama a la IA: se usa lo guardado en el navegador |
| CA21 | Abrir un cuadre del historial y añadirle tickets | Se suman a los que tenía y se recalcula |
| CA27 | Uruguay: factura de luz de 1.220 pagada por débito automático (el banco cobra 1.200) | Emparejados con «descuento IVA débito automático (20,00)» |
| CA28 | Factura de agua de 2.378,00 (1.707,98 gravados) cobrada el día que vence por 2.343,84 | En Uruguay, emparejada con descuento (34,16); en España, «🟡 Por confirmar» con botones ✅ / ❌ |

## Cómo se usa

1. Descarga de tu banco los movimientos del mes (CSV, Excel o PDF) y súbelos en el **Paso 1**.
2. Sube las fotos de los tickets y las facturas en PDF en el **Paso 2** (máx. 20). Es opcional: puedes cuadrar solo con el extracto y añadirlos después.
3. Pulsa **✨ Cuadrar gastos**, revisa las pestañas y descarga el Excel.

¿Sin datos a mano? Pulsa **🧪 Probar con datos de ejemplo**: todos son inventados.

## Cómo funciona

| Pieza | Detalle |
|---|---|
| Interfaz | Streamlit (una página) con tema propio claro/oscuro (`.streamlit/config.toml`) y estilos en `estilo.py`: cabecera, tarjetas, pestañas en píldora y lo secundario detrás de botones |
| Lectura (IA) | Pydantic AI: Gemini `gemini-3.8-flash` y, si falla, Claude `claude-haiku-5-5` de reserva (`FallbackModel`); multimodal, salida con esquema; 5 comprobantes por llamada |
| Cuadre (Python) | `cuadre.py`: (1) uno a uno: mismo importe (±1 céntimo) y fecha de emisión o de vencimiento a ≤ 4 días; si no es seguro pero el nombre (del comercio o del archivo) coincide, se empareja «por confirmar» y el usuario lo confirma o descarta; (2) reembolsos: varios tickets anteriores que suman exactamente un pago (p. ej. una transferencia a quien adelantó las compras) |
| Errores | Mensajes claros para cuota agotada (con reintento), clave, archivos dañados, demasiado grandes o ilegibles |
| Clave | En *Settings → Secrets* de Streamlit, nunca en el código |

## Próximamente

Funcionalidades previstas (aún **no** están en la app):

- **Enviar a un programa de contabilidad:** además del Excel, cargar los gastos cuadrados en un programa de contabilidad externo.
- **Preguntas sobre los gastos:** responder en lenguaje natural preguntas como «¿cuánto gasté en transporte en octubre?».

## Ejecutar en local

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # pega tu clave de https://aistudio.google.com/apikey
streamlit run app.py
```

Para regenerar los datos de ejemplo: `python ejemplos/generar_ejemplos.py`.

## Cómo la he construido

- **Herramientas:** Claude Code (extensión de VS Code) para programar; la app usa la API de Gemini (`gemini-3.8-flash`).
- **Fichero de contexto del agente:** [AGENTS.md](AGENTS.md), con las reglas del proyecto. [CLAUDE.md](CLAUDE.md) (Claude Code) y [GEMINI.md](GEMINI.md) (Gemini CLI) lo importan, así que todos los agentes siguen las mismas reglas.
- **Prompts clave:**
  1. «Crea el scaffold del proyecto a partir de `Enunciado del reto.pdf` y `Rúbrica del reto.pdf`. Crea los archivos mencionados con sus apartados vacíos. No implementes funcionalidades todavía, no escribas ninguna clave y usa solo datos inventados.»
  2. «Completa el documento `ESPECIFICACION.md` para la siguiente app: dado un extracto bancario (CSV, Excel o PDF) y hasta 20 fotos de tickets o facturas en PDF, empareje cada gasto del extracto con su comprobante, liste los gastos sin comprobante y los comprobantes que no están en el banco, y agrupe los gastos por categoría. Gemini solo lee los documentos y devuelve JSON con esquema; el emparejamiento lo hace Python con reglas fijas (mismo importe y fecha cercana). Crea datos de ejemplo inventados que incluyan estos casos.»
  3. «Añade a `cuadre.py` el caso de los reembolsos: varios tickets se pagan con un solo movimiento, por ejemplo una transferencia a quien adelantó las compras. Si un gasto sigue sin comprobante, busca una combinación de 2 o más tickets anteriores que sumen exactamente su importe. Cada ticket debe contar en su propia categoría. Si hay varias combinaciones posibles, elige una y marca «revisar». Añade un caso de ejemplo y actualiza los criterios de aceptación de `ESPECIFICACION.md`.»
- **Qué delegué al agente y qué revisé a mano:**
  - *Delegado:* la estructura de `app.py`, el manejo de errores de la API, el generador de tickets de ejemplo y la redacción inicial de la especificación.
  - *Decidido por mí:* que el emparejamiento no lo haga la IA sino reglas fijas en `cuadre.py`, para que el resultado sea comprobable. Detalles menores en los archivos generados.

## Documentación del proyecto

- [ESPECIFICACION.md](ESPECIFICACION.md): funcionalidades, casos límite, criterios de aceptación y prompts
- [AGENTS.md](AGENTS.md): contexto para el agente de programación
- [CLAUDE.md](CLAUDE.md) y [GEMINI.md](GEMINI.md): importan AGENTS.md para Claude Code y Gemini CLI

## Limitaciones

- La IA puede leer mal un importe: revisa la pestaña *Lectura IA*.
- No empareja un ticket pagado en varios cargos (pagos fraccionados).
- En reembolsos, si varias combinaciones de tickets suman lo mismo, elige una y avisa para revisar.
- No es contabilidad oficial ni decide qué es deducible.
- Privacidad: los archivos se envían a Gemini; en la capa gratuita Google puede usarlos para mejorar sus servicios. Prueba con los datos de ejemplo.
- El historial de cuadres, lo leído por la IA y las fotos y PDF de los comprobantes se guardan solo en tu navegador (IndexedDB); se borra en *Ajustes*. En otro navegador o en modo privado no está.

---

Todos los datos de ejemplo son inventados. Proyecto del reto de *Fundamentos de programación (Python para IA)*, OBS Business School.
