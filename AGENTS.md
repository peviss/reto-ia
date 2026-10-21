# AGENTS.md · Contexto para agentes de IA

## Proyecto

**Cuadra tus gastos**: app Streamlit que empareja fotos de tickets y facturas PDF con los
movimientos del extracto bancario, señala lo que falta y agrupa los gastos por categoría.
Reto de la asignatura *Fundamentos de programación (Python para IA)*, OBS. La especificación
completa está en `ESPECIFICACION.md`: léela antes de cambiar nada.

## Usuario final

Autónomo, pequeño negocio o tesorero de una asociación. **No es técnico ni contable.** Todo
texto visible: en español, trato de "usted", sin jerga informática ni contable.

## Arquitectura (respétala)

| Archivo | Qué hace | Reglas |
|---|---|---|
| `app.py` | Interfaz + llamadas a Gemini para **leer** documentos | La IA solo extrae datos con esquema JSON (Pydantic). Nunca decide emparejamientos. |
| `cuadre.py` | **Empareja** (uno a uno y reembolsos agrupados) y **agrupa** con reglas fijas | Python puro, sin IA ni Streamlit, para poder probarlo y explicarlo. |
| `ejemplos/` | Datos inventados + `generar_ejemplos.py` | Si añades un caso, regenera y actualiza ESPECIFICACION §5. |

## Stack

- Python 3.11+, Streamlit, pandas, Pillow, openpyxl.
- SDK `google-genai` (`from google import genai`), modelo `gemini-2.5-flash`, `temperature=0`,
  `response_mime_type="application/json"` + `response_schema`.
- Despliegue: Streamlit Community Cloud desde un repositorio público de GitHub.
- Dependencias: solo las de `requirements.txt`. No añadas otras sin preguntar.

## Reglas obligatorias

1. **Nunca** escribas una clave de API en el código, en un `.md` ni en un commit.
   La clave se lee solo con `st.secrets["GEMINI_API_KEY"]`.
2. **Nunca** uses datos personales ni bancarios reales: NIF `B0000000X`, tarjeta `****4444`,
   nombres de comercios inventados.
3. Todo error se muestra con `st.error` / `st.warning` y un mensaje que un no técnico entienda
   y que diga qué hacer. Nunca enseñes una traza de Python.
4. Valida la entrada **antes** de llamar a la IA (faltan archivos, > 20 comprobantes, > 8 MB).
5. Cuida la cuota gratuita: reduce imágenes, agrupa comprobantes por llamada, no repitas
   llamadas al cambiar ajustes (usa `st.session_state`).
6. Maneja como mínimo: falta de clave, clave inválida, 429 (con un reintento), 400, 5xx y fallo de red.
7. Si cambias un prompt o un esquema, actualiza ESPECIFICACION §4 y §6.
8. Código simple y comentado en español: se evalúa que el autor lo sepa explicar.

## Cómo probar

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # pegar clave
streamlit run app.py          # → "Probar con datos de ejemplo" → "Cuadrar gastos"
```

Después, recorrer los criterios de aceptación CA1–CA14 de `ESPECIFICACION.md`.

## Al terminar una tarea

Resume en 3–5 líneas qué cambiaste y por qué, para copiarlo en la sección «Cómo la he construido» del README.
