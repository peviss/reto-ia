---
name: test
description: Ejecuta y mantiene las pruebas de «Cuadra tus gastos»: las automáticas de tests/ (reglas de cuadre.py, validación y errores de app.py) y la revisión de los criterios de aceptación CA de ESPECIFICACION.md §5. Úsala cuando el usuario pida probar la app, pasar los tests, comprobar si algo funciona o si un cambio ha roto algo, verificar una funcionalidad o un criterio CA, o rellenar PRUEBA.md; y también después de cambiar cuadre.py, app.py o ejemplos/, y antes de hacer commit o entregar.
---

# Pruebas

Hay dos tipos de prueba. Haz siempre primero las automáticas: son gratis y tardan un segundo.

| Tipo | Dónde | Qué cubre |
|---|---|---|
| Automáticas | `tests/test_cuadre.py` | Reglas de emparejamiento y agrupación con los datos de ejemplo |
| Automáticas | `tests/test_app.py` | Validación de la entrada, mensajes de error de la IA y la interfaz con `AppTest` |
| Manuales | La app abierta (`streamlit run app.py`) | Lo que necesita la IA de verdad o una persona |

## Reglas

- **Ninguna prueba automática llama de verdad a Gemini** (gasta cuota y no da siempre lo mismo).
  Usa los datos escritos a mano de `tests/datos_ejemplo.py` y el `ClienteFalso` de `test_app.py`.
  `test_app.py` bloquea `genai.Client` y los secretos: si una prueba falla con «llamada real a
  Gemini», arregla la prueba, no quites el bloqueo.
- Solo biblioteca estándar (`unittest`, `unittest.mock`) y lo que ya trae Streamlit
  (`streamlit.testing.v1.AppTest`). No añadas pytest ni otros paquetes sin preguntar (regla 10 de AGENTS.md).
- Cada prueba de un criterio lleva su ID en el nombre: `test_CA7_factura_pdf`.
- Pruebas en español, sencillas y comentadas: el autor tiene que saber explicarlas.
- Si una prueba falla, **no la cambies para que pase** sin decirlo: primero averigua si el fallo
  está en el código o en la prueba, y explícalo al usuario.

## Ejecutar

```bash
env/bin/python -m unittest discover -s tests -v
```

(Desde la raíz del proyecto. Si no existe `env/`, usa `python`.) Los avisos «missing ScriptRunContext»
y «Session state does not function…» son normales al importar `app.py` y se pueden ignorar.

Resume el resultado en pocas líneas: `N pruebas · X correctas · Y fallan`, y para cada fallo,
qué CA afecta y la causa probable.

## Qué criterio cubre cada prueba

| CA | Automática | Manual |
|---|---|---|
| CA1–CA7, CA13, CA15–CA17 | `test_cuadre.py` (reglas, con lo que *debería* leer la IA) | Con la app y la IA real, comprobar que la IA lee bien los ejemplos |
| CA8, CA9 | `test_app.py` (`validar` y botón «Cuadrar» sin archivos) | — |
| CA10 | `test_cuadre.py` (comprobante `legible=False`) | Subir una foto que no sea un ticket |
| CA11 | `test_app.py` (`AppTest` sin clave) | — |
| CA12 | `test_app.py` (429 dos veces → un reintento y mensaje) | — |
| CA18 | `test_app.py` (Gemini falso sin cuota → responde el Claude falso, sin esperar) | Con las dos claves y una clave de Gemini falsa, «Cuadrar gastos» con el ejemplo |
| CA14 | — | Una persona que no conoce la app, con el ejemplo, < 2 min |

Las pruebas automáticas comprueban las **reglas**; que la **IA lea bien** los archivos solo se ve
con la app real. Una funcionalidad solo pasa a 🧪 Verificada cuando ambas cosas pasan.

## Pruebas manuales

1. Comprueba que existe `.streamlit/secrets.toml` (no muestres ni copies la clave).
2. `env/bin/streamlit run app.py` en segundo plano; abre `http://localhost:8501` (con Claude in
   Chrome si está disponible, en una pestaña nueva).
3. «🧪 Probar con datos de ejemplo» → «Cuadrar gastos». Cada pulsación gasta ~3 llamadas de cuota:
   no lo repitas sin necesidad; para CA13 y CA17 mueve los ajustes **sin** volver a pulsar.
4. Compara las 4 cifras y las pestañas con la tabla de §5. En «Lo que ha leído la IA», revisa que
   importes y fechas coinciden con `tests/datos_ejemplo.py`.
5. Lo que necesite a una persona (CA14) o forzar un error real (CA12) pídeselo al usuario.
6. Para la app al terminar.

## Después de probar

- **PRUEBA.md**: si el usuario lo pide o está preparando la entrega, marca ☑ OK / ☑ Falla en la
  tabla de criterios y escribe en «Nota» si fue automática, manual o ambas. No inventes los
  datos del compañero que probó la app: pregúntalos.
- **ESPECIFICACION §2.1**: si todos los CA de una funcionalidad pasan (automáticos y manuales),
  propón marcarla como 🧪 Verificada siguiendo la skill `features` y anota en «Notas» qué CA se
  comprobaron y cómo.

## Mantener las pruebas

- **Nuevo CA en §5 o nueva funcionalidad** → añade su prueba (en `test_cuadre.py` si es una regla,
  en `test_app.py` si es interfaz o errores) y una fila en la tabla de arriba y en PRUEBA.md.
- **Cambias `ejemplos/generar_ejemplos.py`** → actualiza `tests/datos_ejemplo.py` para que siga
  siendo lo que la IA debería leer.
- **Cambias un texto de aviso o error en `app.py`** → las pruebas buscan un trozo del mensaje
  (`assertIn`); ajústalo si cambia ese trozo.
