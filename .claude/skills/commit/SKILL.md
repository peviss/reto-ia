---
name: commit
description: Hace commits en el repositorio de «Cuadra tus gastos» (reto-ia) con el estilo del proyecto (mensajes en español, una línea, verbo en infinitivo) y comprueba antes que no se sube ninguna clave ni dato real y que ESPECIFICACION.md está al día. Úsala cuando el usuario pida hacer commit, «commitear», «guardar los cambios en git», separar cambios en varios commits o hacer push en este proyecto.
---

# Commits en reto-ia

El repositorio es **público** (`github.com/peviss/reto-ia`) y Streamlit Cloud despliega
desde `main`: lo que se sube lo puede ver cualquiera y llega a la app publicada.

## 1. Mirar qué hay

```bash
git status --short
git diff
git diff --staged
```

## 2. Comprobaciones antes de hacer commit (paran el commit si fallan)

1. **Secretos.** Nunca se sube `.streamlit/secrets.toml` ni `.env`. Busca claves en lo que
   se va a subir: `git diff --staged | grep -nE 'AIza[0-9A-Za-z_-]{20,}|GEMINI_API_KEY *= *"'`.
   Si aparece algo, no hagas commit y avisa.
2. **Datos reales.** En `ejemplos/` y en el código solo datos inventados (NIF `B0000000X`,
   tarjeta `****4444`). Si ves un nombre, NIF, IBAN o tarjeta que parezca real, pregunta.
3. **Archivos que no son del proyecto.** No añadas sin preguntar: los PDF del enunciado y la
   rúbrica, `RETO.md`, `HITO_SEMANA2.md`, `PRUEBA.md`, `.vscode/`, `env/`, `__pycache__/`.
   Son documentos de trabajo del curso; puede que el usuario no quiera publicarlos.
   No uses `git add -A` ni `git add .`: añade los archivos por su nombre.
4. **Pruebas.** Si el commit toca código (`app.py`, `cuadre.py`, `ejemplos/`, `tests/`), ejecuta
   `env/bin/python -m unittest discover -s tests` (o `python` si no hay `env/`). Si alguna falla,
   no hagas commit: explica qué CA afecta y sigue la skill `/test` para arreglarlo.

## 3. Comprobar que la documentación acompaña al código (avisa, no bloquea)

Según las reglas de `AGENTS.md`:

| Si el commit cambia… | …debe cambiar también |
|---|---|
| Una funcionalidad en `app.py` / `cuadre.py` | ESPECIFICACION §2.1 (estado; usa la skill `/features`) y §2 si cambian entradas o salidas |
| Requisitos, reglas de emparejamiento, interfaz o casos límite | La sección correspondiente de ESPECIFICACION (§2, §3, §5) |
| `requirements.txt` | ESPECIFICACION §7 y la línea *Stack* de AGENTS.md |
| Un prompt o un esquema Pydantic | ESPECIFICACION §4 y §6 |
| Los datos de `ejemplos/` | ESPECIFICACION §5 y `tests/datos_ejemplo.py` |
| El modelo de Gemini (`MODELO` en `app.py`) | ESPECIFICACION §4, la línea *Stack* de AGENTS.md y README |
| Un criterio CA nuevo en §5 | Su prueba en `tests/` y su fila en PRUEBA.md (skill `/test`) |
| Una skill en `.claude/skills/` | ESPECIFICACION §6.5 |

Si falta algo, dilo y ofrece actualizarlo en el mismo commit.

## 4. Agrupar

Un commit por cambio con sentido propio. Si el diff mezcla cosas sin relación (p. ej. una
corrección en `cuadre.py` y una regla nueva en AGENTS.md), propón separarlas y en qué orden.
La documentación que acompaña a un cambio de código va en el **mismo** commit que ese código.

## 5. Mensaje

Estilo del historial del proyecto:

- En **español**, **una sola línea**, sin punto final, como mucho ~100 caracteres.
- Empieza por un **verbo en infinitivo**: *Agregar*, *Actualizar*, *Corregir*, *Eliminar*,
  *Mover*, *Renombrar*, *Mejorar*.
- Dice **qué** cambia y, si no es obvio, **para qué**; nombra el archivo o la sección
  cuando ayude.
- Sin prefijos tipo `feat:` / `fix:`.

Ejemplos del historial:

```
Agregar sección de dependencias en ESPECIFICACION.md con detalles sobre paquetes requeridos
Actualizar modelo de Gemini a la versión 3.8-flash
Agregar archivo .gitignore para excluir secretos y archivos temporales
```

Si el cambio necesita explicación (por qué se cambió una regla de emparejamiento, qué criterio
CA arregla), añade un cuerpo breve tras una línea en blanco.

## 6. Hacer el commit y el push

- Enseña al usuario los archivos y el mensaje de cada commit antes de hacerlo si hay más de uno
  o si algo de los pasos 2–3 ha dado aviso.
- Trabaja en `main` (es un proyecto individual); no crees ramas salvo que lo pida.
- **No hagas push** salvo que el usuario lo pida: un push a `main` redespliega la app pública.
- Después, muestra `git log --oneline -n <commits hechos>`.
- Si el commit cambia la app o su forma de construirla, ofrece el resumen de 3–5 líneas para la
  sección «Cómo la he construido» del README (ver «Al terminar una tarea» en AGENTS.md).
