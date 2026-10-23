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
| `app.py` | Interfaz + llamadas a la IA (Gemini, con Claude de reserva) para **leer** documentos | La IA solo extrae datos con esquema JSON (Pydantic). Nunca decide emparejamientos. |
| `cuadre.py` | **Empareja** (uno a uno y reembolsos agrupados) y **agrupa** con reglas fijas | Python puro, sin IA ni Streamlit, para poder probarlo y explicarlo. |
| `ejemplos/` | Datos inventados + `generar_ejemplos.py` | Si añades un caso, regenera y actualiza ESPECIFICACION §5. |

## Stack

- Python 3.11+, Streamlit, pandas, Pillow, openpyxl.
- Pydantic AI (`pydantic-ai-slim[google,anthropic]`): `Agent` con `output_type=list[Esquema]`,
  `temperature=0` y un `FallbackModel`: `gemini-3.8-flash` y, si falla, `claude-haiku-5-5` (Anthropic).
- Despliegue: Streamlit Community Cloud desde un repositorio público de GitHub.
- Dependencias: solo las de `requirements.txt`. No añadas otras sin preguntar.

## Reglas obligatorias

1. **Nunca** escribas una clave de API en el código, en un `.md` ni en un commit.
   Las claves se leen solo con `st.secrets["GEMINI_API_KEY"]` y `st.secrets["ANTHROPIC_API_KEY"]`.
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
9. Si cambian los requisitos (funcionalidades, reglas de emparejamiento, interfaz, casos límite),
   actualiza la sección correspondiente de `ESPECIFICACION.md` en la misma tarea.
10. Si añades, quitas o cambias un paquete en `requirements.txt` (tras preguntar), actualiza
    ESPECIFICACION §7 (*Dependencias*) y la línea *Stack* de este archivo.

## Cómo probar

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v   # pruebas automáticas, sin gastar cuota de la IA
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # pegar claves
streamlit run app.py          # → "Probar con datos de ejemplo" → "Cuadrar gastos"
```

Después, recorrer los criterios de aceptación CA1–CA17 de `ESPECIFICACION.md` que no cubren las
pruebas automáticas. En Claude Code lo guía la skill `/test`.

## Al terminar una tarea

Resume en 3–5 líneas qué cambiaste y por qué, para copiarlo en la sección «Cómo la he construido» del README.

Si la tarea añade, completa o quita una funcionalidad, actualiza su fila y el conteo en
ESPECIFICACION §2.1 (*Estado de las funcionalidades*); en Claude Code lo hace la skill `/features`.
