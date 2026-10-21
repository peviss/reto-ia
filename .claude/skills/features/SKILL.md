---
name: features
description: Lleva el conteo de las funcionalidades (F1, F2…) de «Cuadra tus gastos» y su estado en FEATURES.md. Úsala cuando el usuario pregunte cuántas funcionalidades hay implementadas, qué falta por hacer o el progreso del reto; cuando pida marcar una funcionalidad como planeada, en curso, implementada, verificada o descartada; cuando añada una funcionalidad nueva; y también al terminar de implementar o quitar una funcionalidad en app.py o cuadre.py, para dejar el registro al día.
---

# Conteo de funcionalidades

El registro es `FEATURES.md` en la raíz del proyecto. Es la única fuente del conteo:
no lleves el número en otro sitio.

## Estados

| Estado | Significa | Cuenta como implementada |
|---|---|---|
| 📝 Planeada | Decidida, sin código | No |
| 🚧 En curso | Hay código, pero incompleto | No |
| ✅ Implementada | El código existe y la funcionalidad se puede usar en la app | Sí |
| 🧪 Verificada | Implementada y sus criterios de aceptación (CA…) pasan con los datos de ejemplo | Sí |
| ❌ Descartada | No se va a hacer | No cuenta en el total |

## Qué hacer según la petición

**Sin argumentos o «¿cuántas llevo?»** → informe:

1. Lee `FEATURES.md`.
2. Comprueba cada fila contra el código: que las funciones o pestañas de la columna
   «Dónde está» existen en `app.py` / `cuadre.py` (con grep). Si una marcada como
   ✅ o 🧪 ya no está, o una 📝 ya tiene código, avisa y propón el estado correcto;
   no lo cambies sin decirlo.
3. Compara con `ESPECIFICACION.md` §2 y `HITO_SEMANA2.md`: si allí hay una
   funcionalidad que no está en el registro, dilo.
4. Responde en pocas líneas: `Implementadas X / Y (verificadas Z)` y la lista de
   las que faltan con su estado.

**«Marca F2 como verificada» / «F4 en curso»** → actualiza la fila. Para 🧪 Verificada,
pregunta o comprueba qué criterios CA se han probado y anótalos en «Notas».

**«Añade una funcionalidad: …»** → nueva fila con el siguiente número libre (F6, F7…),
estado 📝 Planeada salvo que se diga otro.

**Después de implementar o quitar código de una funcionalidad** (aunque no lo pidan) →
actualiza su fila y su columna «Dónde está».

**Mantén ESPECIFICACION.md sincronizado** (reglas 9 y 10 de AGENTS.md):
- Si se añade, cambia o descarta una funcionalidad, o cambian sus requisitos, actualiza
  `ESPECIFICACION.md` §2 (y §3 o §5 si afecta a la interfaz o a los criterios CA).
- Si la funcionalidad necesita un paquete nuevo de Python, pregunta antes de añadirlo a
  `requirements.txt`. Cuando lo añadas, actualiza ESPECIFICACION §7 (*Dependencias*) y
  la línea *Stack* de AGENTS.md.

## Al modificar el registro

- Recalcula la línea de cabecera:
  `**Implementadas: X / Y** · Verificadas: Z / Y · Última actualización: AAAA-MM-DD`
  - X = filas ✅ + 🧪; Z = filas 🧪; Y = todas las filas menos ❌.
- Añade una línea al «Historial» con la fecha de hoy y el cambio en una frase.
- Mantén la tabla en español y los números F en orden; no renumeres las existentes.
