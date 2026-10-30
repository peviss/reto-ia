"""Cuadra tus gastos: empareja tickets y facturas con el extracto del banco y los agrupa por categoría.

App Streamlit (Ruta A) con Pydantic AI: Gemini (capa gratuita) y, si falla, Claude (Anthropic) de reserva.
- La IA LEE: saca los movimientos del extracto y los datos de cada ticket o factura.
- Python CUADRA: empareja por importe y fecha y agrupa por categoría (cuadre.py).
Las claves se leen de los secretos de la plataforma: nunca se escriben en el código.
Lo que lee la IA se guarda en el navegador del usuario para no leerlo dos veces (almacen.py).
"""

import base64
import io
import logging
import os
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # sin el anuncio de Pydantic AI en la consola

import pandas as pd
import streamlit as st
from PIL import Image, ImageOps
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.exceptions import (
    FallbackExceptionGroup, ModelAPIError, ModelConnectionError, ModelHTTPError,
    ModelQuotaExceededError, ModelRateLimitError, ModelServerError, ModelUnavailableError,
    UnexpectedModelBehavior,
)
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider

import almacen
import estilo
from cuadre import CATEGORIAS, PAISES, POR_CONFIRMAR, clave_pareja, consultar_gastos, cuadrar

MODELO_GEMINI = "gemini-3.8-flash"
MODELO_RESERVA = "claude-haiku-5-5"  # Anthropic: solo se usa si Gemini falla
MAX_COMPROBANTES = 20
COMPROBANTES_POR_LLAMADA = 5
MAX_MB_ARCHIVO = 8
MAX_LINEAS_EXTRACTO = 300
TURNOS_RECORDADOS = 10  # en la conversación, cuántas preguntas anteriores se le recuerdan a la IA
CARPETA_EJEMPLOS = Path(__file__).parent / "ejemplos"

# Gráfico de tarta por categoría. Más de 6 porciones no se distinguen: las pequeñas van a «Resto».
# Colores en orden fijo, comprobados para daltonismo y legibles sobre el tema claro y el oscuro
# (Streamlit no dice de forma fiable qué tema ve cada persona, así que valen para los dos).
PORCIONES_TARTA = 6
COLORES_TARTA = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"]
GRIS_RESTO = "#8a8980"

# Logs en la consola donde corre «streamlit run» (las librerías, solo avisos)
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("cuadra")
log.setLevel(logging.INFO)

TIPOS_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif", ".pdf": "application/pdf", ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


# ---------- Qué le pedimos a la IA ----------

class Movimiento(BaseModel):
    fecha: str  # AAAA-MM-DD
    concepto: str
    importe: float  # negativo = gasto, positivo = ingreso
    categoria: str


class Comprobante(BaseModel):
    archivo: str
    comercio: str
    fecha: str  # AAAA-MM-DD, o "" si no se lee
    vencimiento: str = ""  # AAAA-MM-DD: en facturas de servicios, el día que se cobra
    total: float
    base_gravada: float = 0.0  # la parte con IVA, sin el IVA (para el descuento de Uruguay)
    categoria: str
    legible: bool


LISTA_CATEGORIAS = ", ".join(CATEGORIAS)

PROMPT_EXTRACTO = f"""Eres un asistente contable. Te paso un extracto bancario \
(de cualquier banco o país; CSV, Excel convertido a texto o PDF). Devuelve TODOS los movimientos, sin saltarte ninguno.

Reglas:
- fecha: la fecha de operación en formato AAAA-MM-DD.
- concepto: el texto del concepto tal cual aparece. Si el extracto tiene una columna de asunto, \
referencia o beneficiario (p. ej. a quién va una transferencia y para qué), añádela detrás con " - ".
- importe: número con punto decimal. Gastos y cargos en NEGATIVO, ingresos en POSITIVO. \
Si el extracto tiene columnas separadas de cargo y abono, aplica el signo tú.
- categoria: elige UNA de esta lista, exactamente escrita así: {LISTA_CATEGORIAS}.
- No inventes movimientos. No incluyas la fila de saldo inicial o final.
"""

PROMPT_COMPROBANTES = f"""Eres un asistente contable. Te paso fotos de tickets y facturas \
(imágenes o PDF). Cada uno va precedido de su nombre de archivo. Devuelve un elemento por archivo.

Reglas:
- archivo: el nombre de archivo exacto que te indico.
- comercio: nombre comercial corto del que emite el documento, como aparece en el logo o como \
saldría en un banco (una marca o una sigla, p. ej. «UTE»), no la razón social larga.
- fecha: fecha de la compra o de emisión de la factura en formato AAAA-MM-DD; "" si no se lee.
- vencimiento: si es una factura con fecha de vencimiento o de cobro, esa fecha en AAAA-MM-DD; "" si no hay.
- total: el TOTAL pagado, IVA incluido, número con punto decimal. No uses subtotales ni la \
cantidad entregada en efectivo.
- base_gravada: la suma de los importes gravados con IVA, SIN el IVA («subtotal gravado», \
«importe gravado», «base imponible»); 0 si no aparece.
- categoria: elige UNA de esta lista, exactamente escrita así: {LISTA_CATEGORIAS}.
- legible: false si no es un ticket o factura o no se puede leer el total (entonces total = 0).
- No inventes datos: si dudas de un número, marca legible = false.
"""

PROMPT_CONVERSACION = f"""Eres un asistente que ayuda a una persona sin conocimientos contables a entender \
sus gastos. Respondes SOLO con los datos del cuadre que van más abajo: los gastos del extracto del banco, \
con qué ticket o factura se han emparejado, los comprobantes que no están en el banco, lo que se ha leído \
de cada comprobante y los ingresos.

Reglas:
- Para cualquier total, suma o recuento de gastos usa SIEMPRE la herramienta sumar_gastos: no sumes tú.
- Categorías válidas: {LISTA_CATEGORIAS}. Fechas en AAAA-MM-DD.
- Un reembolso agrupado ocupa varias filas con el mismo n.º de «Mov.»: es un solo pago.
- Si algo no está en los datos, dilo; no lo inventes. No digas si un gasto es deducible ni des consejos fiscales.
- Responde en español, tratando de usted, en pocas frases y sin jerga. Importes con coma decimal y «€».
"""


# ---------- Lectura de archivos ----------

def archivo_desde_subida(subido):
    """Convierte un archivo subido en Streamlit en un dict sencillo."""
    extension = Path(subido.name).suffix.lower()
    return {"nombre": subido.name, "datos": subido.getvalue(), "mime": TIPOS_MIME.get(extension, subido.type)}


def archivo_desde_disco(ruta):
    return {"nombre": ruta.name, "datos": ruta.read_bytes(), "mime": TIPOS_MIME[ruta.suffix.lower()]}


def cargar_ejemplos():
    extracto = archivo_desde_disco(CARPETA_EJEMPLOS / "extracto_octubre.csv")
    comprobantes = [
        archivo_desde_disco(ruta)
        for ruta in sorted(CARPETA_EJEMPLOS.iterdir())
        if ruta.suffix.lower() in (".jpg", ".pdf")
    ]
    return extracto, comprobantes


def reducir_imagen(archivo):
    """Reduce las fotos del móvil (3–5 MB) a ~300 KB para gastar menos cuota. Si no puede, la deja igual."""
    if not archivo["mime"].startswith("image/"):
        return archivo
    try:
        imagen = ImageOps.exif_transpose(Image.open(io.BytesIO(archivo["datos"])))
        imagen.thumbnail((1600, 1600))
        salida = io.BytesIO()
        imagen.convert("RGB").save(salida, "JPEG", quality=85)
        return {**archivo, "datos": salida.getvalue(), "mime": "image/jpeg"}
    except Exception:  # p. ej. HEIC: Gemini lo lee directamente (Claude no)
        return archivo


def contenido_extracto(archivo):
    """Prepara el extracto para la IA: texto si es CSV/Excel, el PDF tal cual si es PDF."""
    if archivo["mime"] == "application/pdf":
        return BinaryContent(data=archivo["datos"], media_type="application/pdf")
    if archivo["nombre"].lower().endswith(".xlsx"):
        texto = pd.read_excel(io.BytesIO(archivo["datos"]), header=None).to_csv(index=False, header=False)
    else:
        try:
            texto = archivo["datos"].decode("utf-8")
        except UnicodeDecodeError:
            texto = archivo["datos"].decode("latin-1")  # muchos bancos españoles exportan así
    lineas = texto.strip().splitlines()
    if len(lineas) > MAX_LINEAS_EXTRACTO:
        raise ValueError(
            f"El extracto tiene más de {MAX_LINEAS_EXTRACTO} líneas. Descargue solo un mes o un trimestre."
        )
    return "\n".join(lineas)


# ---------- Llamadas a la IA ----------

# Lo que se puede elegir en Ajustes → Avanzado. Cada opción dice qué clave necesita (None = la que haya).
AUTOMATICO = "Automático (recomendado)"
OPCIONES_MODELO = {
    AUTOMATICO: None,  # Gemini y, si falla, Claude
    f"Solo Gemini · {MODELO_GEMINI}": "GEMINI_API_KEY",
    f"Solo Claude · {MODELO_RESERVA}": "ANTHROPIC_API_KEY",
}


def claves_disponibles():
    """Los nombres de las claves de IA que hay en los secretos."""
    disponibles = []
    for nombre_clave in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        try:
            if st.secrets[nombre_clave]:
                disponibles.append(nombre_clave)
        except Exception:  # sin secrets.toml o sin esa clave
            log.info("Sin %s: ese modelo no se usará", nombre_clave)
    return disponibles


def opciones_modelo():
    """Las opciones del desplegable de modelos que se pueden usar con las claves que hay."""
    disponibles = claves_disponibles()
    return [opcion for opcion, clave in OPCIONES_MODELO.items() if clave is None or clave in disponibles]


def obtener_modelo(eleccion=AUTOMATICO):
    """Prepara el modelo de IA con las claves de los secretos, según lo elegido en Ajustes → Avanzado.

    Automático: Gemini y, de reserva, Claude. Basta con una de las dos claves; con las dos, si Gemini
    falla (cuota, caída…) se usa Claude. Si se elige uno solo, se usa ese y no hay reserva.
    Devuelve None si no hay clave para lo elegido.
    """
    crear = {
        "GEMINI_API_KEY": lambda c: GoogleModel(MODELO_GEMINI, provider=GoogleProvider(api_key=c)),
        "ANTHROPIC_API_KEY": lambda c: AnthropicModel(MODELO_RESERVA, provider=AnthropicProvider(api_key=c)),
    }
    pedida = OPCIONES_MODELO.get(eleccion)  # None = automático (o una opción que ya no existe)
    modelos = [crear[clave](st.secrets[clave]) for clave in claves_disponibles() if pedida in (None, clave)]
    if not modelos:
        log.error("No hay clave de IA para «%s»", eleccion)
        return None
    log.info("Modelos (en orden), según «%s»: %s", eleccion, ", ".join(m.model_name for m in modelos))
    return modelos[0] if len(modelos) == 1 else FallbackModel(*modelos)


def codigo_error(e):
    """Saca el código HTTP de un error de Pydantic AI (None si es de red o desconocido).

    Si han fallado los dos modelos, cuenta el último: es el que ha impedido leer los archivos.
    """
    if isinstance(e, FallbackExceptionGroup):
        e = e.exceptions[-1]
    if isinstance(e, (ModelRateLimitError, ModelQuotaExceededError)):
        return 429
    if isinstance(e, ModelHTTPError):
        return e.status_code
    if isinstance(e, (ModelServerError, ModelUnavailableError)):
        return 503
    return None


def mensaje_error(e):
    """Traduce un error de la API a un mensaje que entiende cualquier persona."""
    codigo = codigo_error(e)
    if codigo == 429:
        return "Se ha agotado la cuota gratuita de la IA por ahora. Espere un minuto (o vuelva mañana si persiste) y pruebe de nuevo."
    if codigo in (401, 403) or (codigo == 400 and "API key" in str(e)):
        return "La app no está bien configurada (clave no válida). Avise a quien la mantiene."
    if codigo == 400:
        return "La IA no ha podido abrir alguno de los archivos. Compruebe que no están dañados ni protegidos con contraseña."
    if codigo and codigo >= 500:
        return "El servicio de IA no responde en este momento. Pruebe de nuevo en unos minutos."
    return "No hay conexión con el servicio de IA. Pruebe de nuevo en unos minutos."


# ---------- Qué modelo se usa (para enseñarlo en la pantalla) ----------

def nombre_modelo(nombre_tecnico):
    """«gemini-3.8-flash» → «Gemini (gemini-3.8-flash)»; «claude-haiku-5-5» → «Claude (claude-haiku-5-5)»."""
    for marca in ("Gemini", "Claude"):
        if marca.lower() in nombre_tecnico:
            return f"{marca} ({nombre_tecnico})"
    return nombre_tecnico


def modelo_principal(modelo):
    """El modelo que se prueba primero: el único que hay o el primero del FallbackModel."""
    return nombre_modelo((modelo.models[0] if isinstance(modelo, FallbackModel) else modelo).model_name)


def registrar_llamada(modelo, usado, segundos):
    """Apunta en la sesión qué modelo ha respondido a cada llamada, para el resumen de la lectura."""
    st.session_state.setdefault("llamadas_ia", []).append(
        {"principal": modelo_principal(modelo), "modelo": nombre_modelo(usado), "segundos": segundos})


def resumen_llamadas(llamadas):
    """Una frase con los modelos que han leído los archivos, o que no ha hecho falta la IA."""
    if not llamadas:
        return "🤖 No se ha llamado a la IA: estos archivos ya estaban leídos y guardados en este navegador."
    modelos = sorted({llamada["modelo"] for llamada in llamadas})
    segundos = sum(llamada["segundos"] for llamada in llamadas)
    texto = (f"🤖 Leído con {' y '.join(modelos)}: {len(llamadas)} "
             f"{'llamada' if len(llamadas) == 1 else 'llamadas'} a la IA, {segundos:.0f} s.")
    if any(llamada["modelo"] != llamada["principal"] for llamada in llamadas):
        texto += f" {llamadas[0]['principal']} no respondía y se ha usado el modelo de reserva."
    return texto


QUE_SE_LEE = {"Movimiento": "el extracto", "Comprobante": "los comprobantes"}


def llamar_ia(modelo, contenido, prompt, esquema):
    """Pide a la IA una lista con el esquema dado. Reintenta una vez si se agota la cuota.

    El FallbackModel ya pasa a Claude si Gemini falla; aquí solo se espera si fallan todos.
    Mientras espera, dice con qué modelo se está leyendo; al terminar, apunta cuál ha respondido.
    Devuelve (lista_de_dicts, mensaje_de_error).
    """
    agente = Agent(modelo, output_type=list[esquema], instructions=prompt, model_settings={"temperature": 0})
    que = QUE_SE_LEE.get(esquema.__name__, "los archivos")
    for intento in range(2):
        inicio = time.perf_counter()
        try:
            with st.spinner(f"🤖 Leyendo {que} con {modelo_principal(modelo)}…"):
                respuesta = agente.run_sync(contenido)
            break
        except (ModelAPIError, FallbackExceptionGroup) as e:
            log.warning("Falló la IA (%s, código %s): %r", esquema.__name__, codigo_error(e), e)
            if codigo_error(e) == 429 and intento == 0:
                log.info("Reintento en 30 s por cuota")
                st.info("Hay muchas consultas. Esperando 30 segundos para reintentar…")
                time.sleep(30)
                continue
            return None, mensaje_error(e)
        except UnexpectedModelBehavior as e:  # la respuesta no encaja con el esquema
            log.warning("Respuesta de la IA que no encaja con %s: %s", esquema.__name__, e)
            return None, "La IA no ha devuelto datos para estos archivos. Pruebe con otros o con fotos más nítidas."
        except Exception:
            log.exception("Error inesperado llamando a la IA (%s)", esquema.__name__)
            return None, "No hay conexión con el servicio de IA. Pruebe de nuevo en unos minutos."

    usado = respuesta.response.model_name or "?"
    log.info(
        "%s: %d elementos con %s en %.1f s (tokens: %s entrada, %s salida)",
        esquema.__name__, len(respuesta.output), usado, time.perf_counter() - inicio,
        respuesta.usage.input_tokens, respuesta.usage.output_tokens,
    )
    if MODELO_GEMINI not in usado:
        log.warning("Gemini no estaba disponible: ha respondido el modelo de reserva (%s)", usado)
    registrar_llamada(modelo, usado, time.perf_counter() - inicio)
    if not respuesta.output:
        return None, "La IA no ha devuelto datos para estos archivos. Pruebe con otros o con fotos más nítidas."
    return [elemento.model_dump() for elemento in respuesta.output], None


def leer_extracto(modelo, archivo):
    try:
        contenido = contenido_extracto(archivo)
    except ValueError as e:
        log.info("Extracto rechazado (%s): %s", archivo["nombre"], e)
        return None, str(e)
    except Exception:
        log.exception("No se pudo abrir el extracto %s", archivo["nombre"])
        return None, "No se ha podido abrir el extracto. Descárguelo de nuevo del banco en CSV, Excel o PDF."
    log.info("Leyendo extracto %s (%.1f KB)", archivo["nombre"], len(archivo["datos"]) / 1024)
    return llamar_ia(modelo, [contenido], PROMPT_EXTRACTO, Movimiento)


def leer_comprobantes(modelo, archivos, barra):
    """Lee los comprobantes por lotes para no pasarse de la cuota por minuto."""
    leidos = []
    for inicio in range(0, len(archivos), COMPROBANTES_POR_LLAMADA):
        lote = [reducir_imagen(a) for a in archivos[inicio:inicio + COMPROBANTES_POR_LLAMADA]]
        log.info("Leyendo comprobantes %d-%d de %d: %s", inicio + 1, inicio + len(lote), len(archivos),
                 ", ".join(a["nombre"] for a in lote))
        contenido = []
        for archivo in lote:
            contenido.append(f"Archivo: {archivo['nombre']}")
            contenido.append(BinaryContent(data=archivo["datos"], media_type=archivo["mime"]))
        datos, error = llamar_ia(modelo, contenido, PROMPT_COMPROBANTES, Comprobante)
        if error:
            return None, error
        leidos.extend(datos)
        barra.progress(min(1.0, (inicio + len(lote)) / len(archivos)), text=f"Leyendo comprobantes… {inicio + len(lote)} de {len(archivos)}")

    # Si la IA se ha saltado algún archivo, lo añadimos como no legible para que el usuario lo vea
    nombres_leidos = {c["archivo"] for c in leidos}
    for archivo in archivos:
        if archivo["nombre"] not in nombres_leidos:
            log.warning("La IA se ha saltado %s: se marca como no legible", archivo["nombre"])
            leidos.append({"archivo": archivo["nombre"], "comercio": "", "fecha": "", "total": 0.0, "categoria": "Otros", "legible": False})
    return leidos, None


def leer_extracto_con_memoria(modelo, archivo):
    """Como leer_extracto, pero si este mismo extracto ya se leyó antes, usa lo guardado."""
    clave = almacen.huella("extracto", archivo)
    guardado = almacen.lectura(clave)
    if guardado is not None:
        log.info("Extracto %s: ya se había leído, no se llama a la IA", archivo["nombre"])
        return guardado, None
    movimientos, error = leer_extracto(modelo, archivo)
    if not error:
        almacen.guardar_lecturas({clave: movimientos})
    return movimientos, error


def leer_comprobantes_con_memoria(modelo, archivos, barra):
    """Como leer_comprobantes, pero solo manda a la IA los que no se han leído antes."""
    claves = {a["nombre"]: almacen.huella("comprobante", a) for a in archivos}
    ya_leidos, por_leer = [], []
    for archivo in archivos:
        guardado = almacen.lectura(claves[archivo["nombre"]])
        if guardado is None:
            por_leer.append(archivo)
        else:  # el nombre puede haber cambiado: manda el de ahora
            ya_leidos.append({**guardado, "archivo": archivo["nombre"]})
    if ya_leidos:
        log.info("%d comprobantes ya se habían leído, no se llama a la IA para ellos", len(ya_leidos))
    if not por_leer:
        return ya_leidos, None

    nuevos, error = leer_comprobantes(modelo, por_leer, barra)
    if error:
        return None, error
    # Los ilegibles no se guardan: así, si se vuelven a subir, la IA lo intenta de nuevo
    almacen.guardar_lecturas({claves[c["archivo"]]: c for c in nuevos if c["legible"] and c["archivo"] in claves})
    return ya_leidos + nuevos, None


def datos_para_conversar(movimientos, leidos, gastos, sueltos):
    """Todo lo extraído del cuadre, en texto (CSV), para dárselo a la IA en la conversación.

    Un cuadre tiene como mucho unos cientos de filas: cabe entero y no hace falta buscar trozos.
    """
    ingresos = pd.DataFrame([m for m in movimientos if m["importe"] >= 0], columns=["fecha", "concepto", "importe"])
    return "\n\n".join([
        "## Gastos del extracto y su comprobante\n" + gastos.to_csv(index=False),
        "## Comprobantes que no aparecen en el extracto\n" + sueltos.to_csv(index=False),
        "## Lo que se ha leído de cada comprobante\n" + pd.DataFrame(leidos).to_csv(index=False),
        "## Ingresos del extracto\n" + ingresos.to_csv(index=False),
    ])


def conversar(modelo, pregunta, turnos, gastos, datos):
    """Responde a una pregunta sobre el cuadre abierto, recordando las anteriores (F5).

    La IA entiende la pregunta y redacta; los totales los calcula Python con la herramienta sumar_gastos.
    Devuelve (turno, mensaje_de_error): el turno lleva la pregunta, la respuesta, las consultas hechas
    (para enseñar qué gastos se han sumado) y los mensajes para recordárselos a la IA la próxima vez.
    Todo en un formato que se puede pasar a JSON, para guardarlo en el navegador.
    """
    consultas = []
    agente = Agent(modelo, instructions=f"{PROMPT_CONVERSACION}\n# Datos del cuadre\n\n{datos}",
                   model_settings={"temperature": 0})

    @agente.tool_plain
    def sumar_gastos(categoria: str | None = None, desde: str | None = None, hasta: str | None = None,
                     texto: str | None = None, justificante: Literal["con", "sin"] | None = None) -> dict:
        """Total en euros, n.º de gastos y filas de los gastos del extracto que cumplen los filtros.

        Args:
            categoria: una de las categorías válidas; nada = todas.
            desde: primera fecha incluida (AAAA-MM-DD).
            hasta: última fecha incluida (AAAA-MM-DD).
            texto: palabra del comercio o del concepto del banco, por ejemplo "cafeteria".
            justificante: "con" = solo los que tienen ticket o factura; "sin" = solo los que no.
        """
        resultado = consultar_gastos(gastos, categoria, desde, hasta, texto, justificante)
        log.info("Conversación: sumar_gastos(%s, %s, %s, %s, %s) = %s €", categoria, desde, hasta, texto,
                 justificante, resultado["total_euros"])
        consultas.append(resultado)
        return resultado

    # Solo las últimas preguntas, para no gastar cuota de más
    historial = ModelMessagesTypeAdapter.validate_python(
        [m for turno in turnos[-TURNOS_RECORDADOS:] for m in turno["mensajes"]])
    for intento in range(2):
        try:
            respuesta = agente.run_sync(pregunta, message_history=historial)
            break
        except (ModelAPIError, FallbackExceptionGroup) as e:
            log.warning("Falló la IA en la conversación (código %s): %r", codigo_error(e), e)
            if codigo_error(e) == 429 and intento == 0:
                st.info("Hay muchas consultas. Esperando 30 segundos para reintentar…")
                time.sleep(30)
                consultas.clear()
                continue
            return None, mensaje_error(e)
        except UnexpectedModelBehavior as e:
            log.warning("Respuesta de la IA que no se entiende en la conversación: %s", e)
            return None, "La IA no ha sabido responder. Pruebe a preguntarlo de otra forma."
        except Exception:
            log.exception("Error inesperado en la conversación")
            return None, "No hay conexión con el servicio de IA. Pruebe de nuevo en unos minutos."

    log.info("Conversación: respondido con %s (tokens: %s entrada, %s salida)", respuesta.response.model_name,
             respuesta.usage.input_tokens, respuesta.usage.output_tokens)
    # Sin las instrucciones (llevan todos los datos del cuadre): en cada pregunta se mandan las de ahora
    mensajes = [replace(m, instructions=None) if isinstance(m, ModelRequest) else m for m in respuesta.new_messages()]
    return {"pregunta": pregunta, "respuesta": respuesta.output, "consultas": consultas,
            "modelo": nombre_modelo(respuesta.response.model_name or "?"),  # para enseñar quién ha respondido
            "mensajes": ModelMessagesTypeAdapter.dump_python(mensajes, mode="json")}, None


def validar(extracto, comprobantes, editando=False):
    """Comprueba la entrada antes de gastar cuota. Devuelve un aviso o None.

    Si se está editando un cuadre guardado, ya tiene extracto: basta con subir algo nuevo.
    Los tickets y facturas son opcionales: solo con el extracto se ve el gasto por categoría
    (todos los gastos saldrán sin comprobante) y se pueden añadir después.
    """
    if editando and extracto is None and not comprobantes:
        return "Suba más tickets o facturas (o un extracto nuevo) para añadirlos a este cuadre."
    if not editando and extracto is None:
        return "Falta el extracto del banco. Súbalo en el paso 1 o pulse «Probar con datos de ejemplo»."
    if len(comprobantes) > MAX_COMPROBANTES:
        return f"Ha subido {len(comprobantes)} comprobantes. El máximo es {MAX_COMPROBANTES} cada vez: hágalo por partes (por ejemplo, por semanas)."
    for archivo in [a for a in [extracto, *comprobantes] if a is not None]:
        if len(archivo["datos"]) > MAX_MB_ARCHIVO * 1024 * 1024:
            return f"El archivo «{archivo['nombre']}» pesa más de {MAX_MB_ARCHIVO} MB. Haga la foto de nuevo o reduzca el PDF."
    return None


def juntar_comprobantes(anteriores, nuevos):
    """Añade los comprobantes nuevos a los de un cuadre. Si un archivo se llama igual, manda el nuevo."""
    nombres_nuevos = {c["archivo"] for c in nuevos}
    return [c for c in anteriores if c["archivo"] not in nombres_nuevos] + nuevos


def a_excel(gastos, resumen, sueltos):
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as excel:
        resumen.to_excel(excel, sheet_name="Por categoría", index=False)
        gastos.to_excel(excel, sheet_name="Gastos", index=False)
        sueltos.to_excel(excel, sheet_name="Comprobantes sueltos", index=False)
    return salida.getvalue()


# ---------- Interfaz ----------

@st.dialog("Comprobante", width="large")
def ver_comprobante(nombre, archivos, leidos, gastos, huellas):
    """Muestra el ticket o la factura y, debajo, lo que ha leído la IA y con qué gasto va.

    Si el archivo se ha subido en esta sesión, se muestra desde aquí; si no, desde el navegador (IndexedDB).
    """
    st.subheader(nombre)
    archivo = archivos.get(nombre)
    if archivo is None and nombre in huellas:
        almacen.ver_archivo(huellas[nombre], nombre)
    elif archivo is None:  # cuadre guardado con una versión anterior, sin archivos
        st.warning("Este comprobante se guardó sin su archivo. "
                   "Vuelva a subirlo y pulse «Añadir al cuadre» (no se volverá a leer con la IA).")
    elif archivo["mime"] == "application/pdf":
        pdf = base64.b64encode(archivo["datos"]).decode()
        st.html(f'<iframe src="data:application/pdf;base64,{pdf}" width="100%" height="600"></iframe>')
    else:
        try:
            st.image(ImageOps.exif_transpose(Image.open(io.BytesIO(archivo["datos"]))))
        except Exception:  # p. ej. HEIC: el navegador no lo sabe mostrar
            st.info("Esta foto no se puede mostrar aquí, pero puede descargarla.")
    if archivo is not None:
        st.download_button("⬇️ Descargar el archivo", data=archivo["datos"], file_name=nombre, mime=archivo["mime"])

    st.write("**Lo que ha leído la IA**")
    leido = next((c for c in leidos if c["archivo"] == nombre), None)
    if leido:
        st.dataframe(pd.DataFrame([{
            "Comercio": leido["comercio"], "Fecha": leido["fecha"], "Total (€)": leido["total"],
            "Categoría": leido["categoria"], "Se ha podido leer": "Sí" if leido["legible"] else "No",
        }]), hide_index=True)
    st.write("**Gasto del banco con el que va**")
    gasto = gastos[gastos["Comprobante"] == nombre]
    if gasto.empty:
        st.caption("No aparece en el extracto (puede ser un pago en efectivo, de otra tarjeta o de otro mes).")
    else:
        st.dataframe(gasto, hide_index=True)


def mostrar_turno(turno):
    """Una pregunta y su respuesta en la conversación."""
    with st.chat_message("user"):
        st.markdown(turno["pregunta"])
    mostrar_respuesta(turno)


def mostrar_respuesta(turno):
    """La respuesta de la IA, con los gastos que ha sumado la app para responder."""
    with st.chat_message("assistant"):
        st.markdown(turno["respuesta"])
        if turno.get("modelo"):  # las conversaciones guardadas antes no lo tienen
            st.caption(f"🤖 Respondido con {turno['modelo']}")
        filas = [f for consulta in turno["consultas"] for f in consulta["filas"]]
        if filas:
            with st.expander("Gastos que ha sumado la app para responder"):
                st.dataframe(pd.DataFrame(filas).drop_duplicates(), hide_index=True)


# Icono y color de cada categoría en la lista de movimientos (el color, de la paleta del gráfico)
ICONOS = {
    "Alimentación": ("🛒", "#199e70"), "Restauración": ("🍴", "#c98500"),
    "Transporte y combustible": ("⛽", "#d95926"), "Suministros (luz, agua, gas)": ("💡", "#8b5cf6"),
    "Telecomunicaciones y software": ("📶", "#3987e5"), "Material y oficina": ("📎", "#d55181"),
    "Salud": ("💊", "#ef4444"), "Impuestos y cuotas": ("🏛️", "#8a8980"), "Compras online": ("📦", "#3987e5"),
    "Otros": ("💳", "#8a8980"),
}
MESES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.", "oct.", "nov.", "dic."]
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def fecha_larga(texto):
    """'2026-10-10' → ('10 oct. 2026', 'sábado'). Si no es una fecha, la deja como está."""
    try:
        dia = date.fromisoformat(str(texto)[:10])
    except ValueError:
        return str(texto), ""
    return f"{dia.day} {MESES[dia.month - 1]} {dia.year}", DIAS_SEMANA[dia.weekday()]


def frase(texto):
    """'COMPRA TARJ. 4444 SUPERM' → 'Compra tarj. 4444 superm': los conceptos del banco vienen en mayúsculas."""
    texto = str(texto).strip()
    return texto[:1].upper() + texto[1:].lower() if texto.isupper() else texto


def tarjetas_movimientos(movimientos, gastos, leidos, huellas):
    """Prepara cada movimiento del extracto para la lista de tarjetas (estilo.lista_movimientos).

    Los gastos salen de la tabla del cuadre (un reembolso agrupado son varias filas con el mismo «Mov.»
    y aquí es una sola tarjeta con sus comprobantes); los ingresos, del extracto. De más reciente a más antiguo.
    """
    por_archivo = {c["archivo"]: c for c in leidos}
    tarjetas = []
    for numero, filas in gastos.groupby("Mov.", sort=False):
        primera = filas.iloc[0]
        estado = primera["Estado"]
        comprobantes = []
        for archivo in [a for a in filas["Comprobante"] if a]:
            leido = por_archivo.get(archivo, {})
            fecha, _ = fecha_larga(leido.get("fecha", ""))
            comprobantes.append({
                "archivo": archivo, "huella": huellas.get(archivo, ""),
                "es_pdf": archivo.lower().endswith(".pdf"),
                "detalle": " · ".join(x for x in [frase(leido.get("comercio", "")), fecha] if x),
                "importe": euros(leido.get("total", 0)),
            })
        # Las etiquetas dicen de un vistazo cómo está el gasto
        n = len(comprobantes)
        chips = [{"texto": f"{n} {'comprobante' if n == 1 else 'comprobantes'}", "tipo": "ok"}] if n else []
        if estado.startswith("⚠️"):
            chips = [{"texto": "Falta comprobante", "tipo": "falta"}]
        elif estado.startswith(POR_CONFIRMAR):
            chips.append({"texto": "Por confirmar", "tipo": "aviso"})
        elif estado.startswith("🔗"):
            chips.append({"texto": "Reembolso" + (" · revisar" if "revisar" in estado else ""),
                          "tipo": "aviso" if "revisar" in estado else "info"})
        if "descuento IVA" in estado:
            chips.append({"texto": "Descuento IVA " + estado.rsplit("(", 1)[-1].rstrip(")"), "tipo": "info"})
        if "confirmado" in estado:
            chips.append({"texto": "Confirmado", "tipo": "info"})
        # Con un solo comprobante, el nombre del comercio se lee mejor que el concepto del banco
        comercio = frase(por_archivo.get(comprobantes[0]["archivo"], {}).get("comercio", "")) if n == 1 else ""
        icono, tono = ICONOS.get(primera["Categoría"], ICONOS["Otros"])
        fecha, semana = fecha_larga(primera["Fecha"])
        tarjetas.append({
            "id": f"g{numero}", "icono": icono, "tono": tono, "fecha": fecha, "semana": semana,
            "titulo": comercio or frase(primera["Concepto"]),
            "subtitulo": primera["Categoría"] + (f" · {frase(primera['Concepto'])}" if comercio else ""),
            "chips": chips, "importe": "− " + euros(filas["Importe (€)"].sum()), "ingreso": False,
            "comprobantes": comprobantes, "orden": str(primera["Fecha"]),
            "sin_comprobantes": "No tiene ticket ni factura. Puede añadirlo en «➕ Añadir más tickets».",
            "nota": estado.removeprefix(f"{POR_CONFIRMAR}: ").capitalize() if estado.startswith(POR_CONFIRMAR) else "",
        })
    for i, mov in enumerate(m for m in movimientos if m["importe"] >= 0):
        fecha, semana = fecha_larga(mov["fecha"])
        tarjetas.append({
            "id": f"i{i}", "icono": "💰", "tono": "#16a34a", "fecha": fecha, "semana": semana,
            "titulo": frase(mov["concepto"]), "subtitulo": "Ingreso", "chips": [],
            "importe": "+ " + euros(mov["importe"]), "ingreso": True, "comprobantes": [],
            "orden": str(mov["fecha"]), "sin_comprobantes": "Los ingresos no necesitan comprobante.", "nota": "",
        })
    return sorted(tarjetas, key=lambda t: t["orden"], reverse=True)


def tabla_con_comprobantes(tabla, columna, clave):
    """Tabla en la que, al pulsar una celda de `columna`, se abre ese comprobante."""
    def al_pulsar():
        celdas = st.session_state[clave].selection.cells
        if celdas and celdas[0][1] == columna:
            st.session_state.abrir_comprobante = tabla.iloc[celdas[0][0]][columna]

    st.dataframe(tabla, hide_index=True, key=clave, on_select=al_pulsar, selection_mode="single-cell")


def decidir(clave, correcto):
    """Guarda en el cuadre abierto si un emparejamiento «por confirmar» es correcto o no."""
    activo = almacen.cuadre(st.session_state.get("cuadre_activo"))
    if activo:
        lista = "confirmados" if correcto else "rechazados"
        almacen.guardar_cuadre({**activo, lista: [*activo.get(lista, []), clave]})


def por_confirmar(gastos):
    """Los emparejamientos de los que la app no está segura, cada uno con sus botones Sí / No.

    Al confirmar, el gasto queda «con comprobante»; al descartar, el comprobante vuelve a estar
    libre y la app busca otro (o el gasto queda sin comprobante). Se guarda con el cuadre.
    """
    dudosos = gastos[gastos["Estado"].str.startswith(POR_CONFIRMAR)]
    if dudosos.empty:
        return
    with st.container(border=True, key="por_confirmar"):
        st.markdown(f"**🟡 {len(dudosos)} {'emparejamiento' if len(dudosos) == 1 else 'emparejamientos'} "
                    "por confirmar**", help="La app cree que van juntos, pero no está segura. "
                    "Pulse ✅ si es correcto o ❌ si no lo es. Puede ver el comprobante con 👁️.")
        for i, fila in dudosos.iterrows():
            clave = clave_pareja(fila["Fecha"], fila["Concepto"], fila["Importe (€)"], fila["Comprobante"])
            motivo = fila["Estado"].removeprefix(f"{POR_CONFIRMAR}: ")
            c_texto, c_botones = st.columns([5, 1], vertical_alignment="center")
            c_texto.markdown(f"{fila['Fecha']} · {fila['Concepto']} · **{euros(fila['Importe (€)'])}**  \n"
                             f"↔ 🧾 {fila['Comprobante']} · :gray[{motivo}]")
            with c_botones, st.container(horizontal=True, horizontal_alignment="right", gap="small"):
                st.button("👁️", key=f"ver_{i}", help="Ver el comprobante",
                          on_click=lambda nombre=fila["Comprobante"]: st.session_state.update(abrir_comprobante=nombre))
                st.button("✅", key=f"si_{i}", help="Sí, van juntos", on_click=decidir, args=(clave, True))
                st.button("❌", key=f"no_{i}", help="No es este comprobante", on_click=decidir, args=(clave, False))


def euros(importe):
    """12345.6 → «12.345,60 €», como se escribe en España."""
    return f"{importe:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def grafico_categorias(resumen):
    """Tarta (con hueco en el centro) de lo gastado en cada categoría, de mayor a menor.

    La leyenda lleva el porcentaje de cada categoría y, al pasar el ratón, se ve el detalle.
    """
    datos = resumen[["Categoría", "Total (€)", "Gastos"]]  # ya viene de mayor a menor
    colores = COLORES_TARTA[:len(datos)]
    if len(datos) > PORCIONES_TARTA:
        resto = datos.iloc[PORCIONES_TARTA - 1:]
        fila_resto = {"Categoría": f"Resto ({len(resto)} categorías)",
                      "Total (€)": resto["Total (€)"].sum(), "Gastos": resto["Gastos"].sum()}
        datos = pd.concat([datos.iloc[:PORCIONES_TARTA - 1], pd.DataFrame([fila_resto])])
        colores = COLORES_TARTA[:PORCIONES_TARTA - 1] + [GRIS_RESTO]
    datos = datos.reset_index(drop=True)
    datos["orden"] = datos.index
    porcentaje = datos["Total (€)"] / datos["Total (€)"].sum() * 100
    datos["Porcentaje"] = porcentaje.map(lambda x: f"{x:.0f} %".replace(".", ","))
    datos["Etiqueta"] = datos["Categoría"] + " · " + datos["Porcentaje"]
    datos["Total"] = datos["Total (€)"].map(euros)

    st.vega_lite_chart(datos, {
        # Tamaño fijo que cabe en la columna (también en el móvil); la leyenda va debajo.
        # El radio se calcula con el hueco que deja la leyenda: con un radio fijo, la tarta se corta
        "width": 300,
        "height": 300,
        "mark": {"type": "arc", "outerRadius": {"expr": "min(width, height) / 2 - 2"},
                 "innerRadius": {"expr": "min(width, height) / 4"}, "cornerRadius": 4,
                 "padAngle": 0.015},  # un hueco entre porciones, del color del fondo sea cual sea el tema
        "encoding": {
            "theta": {"field": "Total (€)", "type": "quantitative", "stack": True},
            "order": {"field": "orden", "type": "quantitative"},
            "color": {"field": "Etiqueta", "type": "nominal", "sort": datos["Etiqueta"].tolist(),
                      "scale": {"range": colores}, "legend": {"title": None, "orient": "bottom", "columns": 1, "labelLimit": 300}},
            "tooltip": [
                {"field": "Categoría", "type": "nominal"},
                {"field": "Total", "type": "nominal", "title": "Gastado"},
                {"field": "Porcentaje", "type": "nominal", "title": "Del total"},
                {"field": "Gastos", "type": "quantitative", "title": "N.º de gastos"},
            ],
        },
    }, width="content", height=300 + 45 * len(datos))  # la tarta y una línea de leyenda por porción


st.set_page_config(page_title="Cuadra tus gastos", page_icon="🧾", layout="wide")
estilo.aplicar()

def ayuda():
    """El texto de «Cómo funciona»: va en un botón para no ocupar la página."""
    st.markdown(
        "1. **Extracto:** en la web de su banco, descargue los movimientos del mes en CSV, Excel o PDF.\n"
        "2. **Comprobantes:** haga una foto a cada ticket (que se vea el total y la fecha) o suba la factura en PDF.\n"
        "3. Pulse **Cuadrar gastos** y espere unos segundos.\n"
        "4. Revise el resultado y descárguelo en Excel.\n\n"
        "**Cómo empareja:** un ticket y un gasto van juntos si tienen **el mismo importe** y las fechas "
        "se separan pocos días (los pagos con tarjeta pueden tardar 1–3 días en aparecer en el banco). "
        "Si alguien adelantó varias compras y luego se le **reembolsó el total** con una transferencia, "
        "la app busca los tickets anteriores que **suman** ese importe.\n\n"
        "⚠️ **Privacidad:** los archivos se envían a la IA de Google (Gemini) para leerlos y, "
        "si no responde, a la de Anthropic (Claude). En la versión gratuita, Google puede usarlos para mejorar sus servicios. "
        "**Para probar, use los datos de ejemplo**; con datos reales, tape antes el número de cuenta y su DNI.\n\n"
        "💾 **Qué se guarda:** cada cuadre, lo que ha leído la IA, las fotos y PDF de los comprobantes y sus preguntas en «Pregunte» se guardan "
        "**solo en este navegador** (no en nuestro servidor). Si el ordenador es compartido, elimine sus cuadres al terminar. "
        "En la barra lateral, **Mis cuadres**, puede abrir uno, añadirle más tickets o empezar uno nuevo. "
        "Los archivos ya leídos no se vuelven a mandar a la IA. Puede borrarlo todo en ⚙️ Ajustes."
    )



# ---------- Historial de cuadres (barra lateral) ----------

def empezar(id_cuadre=None):
    """Abre un cuadre guardado, o uno nuevo y vacío si id_cuadre es None."""
    st.session_state.cuadre_activo = id_cuadre
    st.session_state.archivos = {}  # los archivos subidos son de otro cuadre
    st.session_state.ejemplo = False
    st.session_state.conversacion = almacen.conversacion(id_cuadre)  # la de este cuadre, si se guardó
    st.session_state.subida = st.session_state.get("subida", 0) + 1  # vacía las subidas de archivos
    st.session_state.ultima_lectura = None  # el resumen de los modelos usados es del cuadre anterior


def renombrar():
    nombre = st.session_state[f"nombre_{st.session_state.get('subida', 0)}"].strip()
    activo = almacen.cuadre(st.session_state.get("cuadre_activo"))
    if activo and nombre:
        almacen.guardar_cuadre({**activo, "nombre": nombre})


with st.sidebar:
    estilo.marca()
    st.button("➕ Nuevo cuadre", on_click=empezar, width="stretch", type="primary")
    st.markdown("##### 🗂️ Mis cuadres")
    historial = almacen.cuadres()
    if not almacen.cargado() and not historial:
        st.caption("Buscando cuadres guardados…")
    elif not historial:
        st.caption("Aún no hay cuadres guardados. Cuando cuadre sus gastos, aparecerán aquí.")
    for guardado in historial:
        abierto = guardado["id"] == st.session_state.get("cuadre_activo")
        st.button(
            f"{'📂' if abierto else '📄'} {guardado['nombre']}", key=f"abrir_{guardado['id']}",
            on_click=empezar, args=(guardado["id"],), width="stretch",
            disabled=abierto, help="Abrir este cuadre",
        )
        st.caption(f"{guardado.get('fecha') or 'Ahora'} · {len(guardado['leidos'])} comprobantes")

activo = almacen.cuadre(st.session_state.get("cuadre_activo"))
subida = st.session_state.get("subida", 0)  # cambia la clave de las subidas para vaciarlas

# La cabecera grande solo en la página vacía: con un cuadre abierto, el nombre ya está en la barra lateral
if not activo:
    with st.container(key="cabecera"):
        st.title("🧾 Cuadra tus gastos")
        st.markdown("Su extracto del banco y sus tickets, cuadrados en un minuto y listos para la gestoría.")

def probar_ejemplo():
    empezar()  # el ejemplo es siempre un cuadre nuevo
    st.session_state.ejemplo = True


# Encabezado del cuadre: el nombre a la izquierda y, a la derecha, botones pequeños.
# Lo que no se usa a menudo (renombrar, eliminar, la ayuda) va dentro de un botón que abre un panel.
c_nombre, c_botones = st.columns([3, 2], vertical_alignment="center")
with c_nombre:
    st.subheader(f"📂 {activo['nombre']}" if activo else "Nuevo cuadre")
    if activo:
        st.caption(f"{activo['extracto']} · {len(activo['leidos'])} comprobantes · {activo.get('fecha') or 'ahora'}")
with c_botones, st.container(horizontal=True, horizontal_alignment="right"):
    if activo:
        zona_excel = st.empty()  # el botón del Excel se rellena abajo, cuando ya está hecho el cuadre
        with st.popover("✏️", help="Cambiar el nombre o eliminar este cuadre"):
            st.text_input("Nombre del cuadre", value=activo["nombre"], key=f"nombre_{subida}", on_change=renombrar)
            if st.button("🗑️ Eliminar este cuadre", width="stretch"):
                almacen.eliminar_cuadre(activo["id"])
                empezar()
                st.rerun()
    else:
        st.button("🧪 Probar con datos de ejemplo", on_click=probar_ejemplo,
                  help="Un extracto y 10 tickets inventados, para ver cómo funciona sin usar sus datos.")
    with st.popover("ℹ️", help="Cómo funciona y qué pasa con sus datos"):
        ayuda()

usar_ejemplo = st.session_state.get("ejemplo", False)

# Con un cuadre abierto, lo que importa es el resultado: subir más archivos queda plegado
seccion = st.expander("➕ Añadir más tickets o cambiar el extracto") if activo else st.container()
with seccion:
    col1, col2 = st.columns(2)
    with col1, st.container(border=True, key="paso_extracto", height="stretch"):
        estilo.titulo_tarjeta(
            "🏦", "1 · Extracto del banco", "Solo si quiere cambiarlo" if activo else "CSV, Excel o PDF",
        )
        subido_extracto = st.file_uploader(
            "Extracto del banco", type=["csv", "xlsx", "pdf"], key=f"extracto_{subida}", label_visibility="collapsed",
        )
    with col2, st.container(border=True, key="paso_comprobantes", height="stretch"):
        estilo.titulo_tarjeta(
            "🧾", "2 · " + ("Más tickets y facturas" if activo else "Tickets y facturas"),
            f"Opcional · fotos o PDF, hasta {MAX_COMPROBANTES}",
        )
        subidos_comprobantes = st.file_uploader(
            "Tickets y facturas", type=["jpg", "jpeg", "png", "webp", "heic", "pdf"],
            accept_multiple_files=True, key=f"comprobantes_{subida}", label_visibility="collapsed",
        )

    if subido_extracto or subidos_comprobantes:
        usar_ejemplo = st.session_state.ejemplo = False  # lo que sube el usuario manda sobre el ejemplo

    if usar_ejemplo:
        extracto, comprobantes = cargar_ejemplos()
        st.info(f"Usando datos de ejemplo: «{extracto['nombre']}» y {len(comprobantes)} comprobantes inventados.")
    else:
        extracto = archivo_desde_subida(subido_extracto) if subido_extracto else None
        comprobantes = [archivo_desde_subida(a) for a in subidos_comprobantes or []]

    if st.button("➕ Añadir al cuadre" if activo else "✨ Cuadrar gastos", type="primary", width="stretch", key="accion"):
        aviso = validar(extracto, comprobantes, editando=activo is not None)
        modelo = None if aviso else obtener_modelo(st.session_state.get("modelo_elegido", AUTOMATICO))
        if aviso:
            st.warning(aviso)
        elif modelo is None:
            st.error("La app no está bien configurada (falta la clave). Avise a quien la mantiene.")
        else:
            st.session_state.llamadas_ia = []  # aquí se apunta qué modelo responde a cada llamada
            barra = st.progress(0.0, text=f"Leyendo con {modelo_principal(modelo)}…")
            error, nuevos = None, []
            if extracto is None:  # editando sin extracto nuevo: se queda el que tenía
                movimientos = activo["movimientos"]
            else:
                movimientos, error = leer_extracto_con_memoria(modelo, extracto)
                if not error and not any(m["importe"] < 0 for m in movimientos):
                    error = "No se ha encontrado ningún gasto en el extracto. Compruebe que ha subido el archivo correcto."
            if not error and comprobantes:
                nuevos, error = leer_comprobantes_con_memoria(modelo, comprobantes, barra)
            barra.empty()
            if error:
                st.error(error)
            else:
                id_cuadre = activo["id"] if activo else almacen.nuevo_id()
                almacen.guardar_cuadre({
                    "id": id_cuadre,
                    "nombre": activo["nombre"] if activo else Path(extracto["nombre"]).stem,
                    "extracto": extracto["nombre"] if extracto else activo["extracto"],
                    "movimientos": movimientos,
                    "leidos": juntar_comprobantes(activo["leidos"] if activo else [], nuevos),
                    # Para encontrar el archivo de cada comprobante en el navegador
                    "huellas": {**(activo.get("huellas", {}) if activo else {}),
                                **{a["nombre"]: almacen.huella("comprobante", a) for a in comprobantes}},
                })
                # Las fotos, reducidas (~300 KB); los PDF, tal cual
                almacen.guardar_archivos({almacen.huella("comprobante", a): reducir_imagen(a) for a in comprobantes})
                # Se guardan también los archivos de esta sesión para poder enseñarlos al pulsar sobre ellos
                archivos = st.session_state.get("archivos", {}) if activo else {}
                empezar(id_cuadre)
                st.session_state.archivos = {**archivos, **{a["nombre"]: a for a in comprobantes}}
                st.session_state.ultima_lectura = resumen_llamadas(st.session_state.llamadas_ia)
                st.rerun()


# Abajo en la barra lateral (estilo.py lo pega al fondo): se escribe aquí porque Streamlit añade en orden
with st.sidebar, st.container(key="ajustes"), st.expander("⚙️ Ajustes"):
    pais = st.radio(
        "País", PAISES, horizontal=True, key="pais",
        help="En Uruguay, los servicios (luz, agua, teléfono, internet…) pagados por débito automático "
        "tienen 2 puntos menos de IVA, así que el banco cobra algo menos que la factura. "
        "Con «Uruguay», la app también empareja esos importes.",
    )
    tolerancia = st.slider(
        "Días de diferencia permitidos entre el ticket y el banco", 0, 10, 4,
        help="Un pago con tarjeta del viernes puede aparecer en el banco el lunes.",
    )
    ventana_reembolso = st.slider(
        "Reembolsos: buscar tickets de hasta cuántos días antes del pago", 0, 90, 30,
        help="Cuando alguien adelanta varias compras y luego se le transfiere el total, "
        "la app busca tickets anteriores al pago que sumen ese importe. 0 = no buscar.",
    )
    # Avanzado: un botón que abre un panel (dentro de un desplegable no se puede poner otro desplegable)
    with st.popover("🔧 Avanzado", width="stretch"):
        opciones = opciones_modelo()
        if st.session_state.get("modelo_elegido") not in opciones:  # p. ej. ya no está esa clave
            st.session_state.modelo_elegido = AUTOMATICO
        st.selectbox(
            "Modelo de IA", opciones, key="modelo_elegido",
            help="Automático es lo recomendado: si Gemini no responde, se usa Claude. "
            "Con un modelo solo, si ese falla no hay reserva. "
            "Los archivos ya leídos no se vuelven a leer al cambiarlo.",
        )
        if st.session_state.modelo_elegido == AUTOMATICO:
            st.caption(f"Se usa Gemini ({MODELO_GEMINI}) y, si no responde, Claude ({MODELO_RESERVA}).")
        if len(opciones) < len(OPCIONES_MODELO):
            st.caption("Solo salen los modelos que tienen su clave configurada.")
    if st.button("🗑️ Borrar lo guardado en este navegador", width="stretch",
                 help="Todos los cuadres y lo que ha leído la IA. Después, los archivos se volverán a leer con la IA."):
        almacen.borrar_todo()
        empezar()
        st.rerun()


# El cuadre abierto se recalcula en cada ejecución: mover el ajuste de días no vuelve a llamar a la IA
if activo:
    movimientos, leidos = activo["movimientos"], activo["leidos"]
    archivos = st.session_state.get("archivos", {})
    gastos, resumen, sueltos = cuadrar(movimientos, leidos, tolerancia, ventana_reembolso, pais,
                                       activo.get("confirmados", []), activo.get("rechazados", []))

    # Un reembolso agrupado ocupa varias filas: contamos movimientos por su n.º («Mov.»)
    con = gastos["Comprobante"] != ""
    total = gastos["Importe (€)"].sum()
    justificado = gastos.loc[con, "Importe (€)"].sum()

    # El Excel va arriba, junto al nombre del cuadre
    zona_excel.download_button(
        "⬇️ Excel",
        data=a_excel(gastos, resumen, sueltos),
        file_name="gastos_cuadrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Para enviarlo a su gestoría: por categoría, todos los gastos y los comprobantes sueltos.",
    )
    # Qué modelo ha leído los archivos: un aviso que se va solo, una vez, justo después de cuadrar
    if st.session_state.get("ultima_lectura"):
        st.toast(st.session_state.pop("ultima_lectura"))
    if not leidos:  # se cuadró solo con el extracto (el paso 2 es opcional)
        st.info("Aún no hay tickets ni facturas: añádalos arriba, en «➕ Añadir más tickets».")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💳 Gastos en el extracto", f"{gastos['Mov.'].nunique()}", euros(total),
              delta_color="off", delta_arrow="off", border=True)
    m2.metric("✅ Con comprobante", f"{gastos.loc[con, 'Mov.'].nunique()}", euros(justificado),
              delta_color="off", delta_arrow="off", border=True)
    m3.metric("⚠️ Sin comprobante", f"{gastos.loc[~con, 'Mov.'].nunique()}", euros(total - justificado),
              delta_color="off", delta_arrow="off", border=True)
    m4.metric("🧾 No están en el banco", f"{len(sueltos)}", border=True, height="stretch",
              help="Tickets o facturas que no aparecen en el extracto: efectivo, otra tarjeta, otro mes…")

    por_confirmar(gastos)

    revisar = gastos[gastos["Estado"].str.contains("revisar")]
    if not revisar.empty:
        st.warning(
            "Algún reembolso agrupado se puede formar con más de una combinación de tickets. "
            "Revise las filas marcadas con «revisar» en la pestaña *Gastos*."
        )

    pestanas = st.tabs(["📊 Categorías", "📋 Movimientos", "⚠️ Qué falta", "💬 Pregunte", "🔍 Lectura IA"])
    with pestanas[0]:
        c_tabla, c_grafico = st.columns([3, 2])
        c_tabla.dataframe(resumen, hide_index=True)
        if not resumen.empty:
            with c_grafico:
                grafico_categorias(resumen)
    with pestanas[1]:
        # Una tarjeta por movimiento; al pulsarla se ven sus comprobantes (y se pueden abrir o descargar)
        tarjetas = tarjetas_movimientos(movimientos, gastos, leidos, activo.get("huellas", {}))
        filtros = {"Todos": lambda t: True, "Gastos": lambda t: not t["ingreso"],
                   "Sin comprobante": lambda t: not t["ingreso"] and not t["comprobantes"],
                   "Ingresos": lambda t: t["ingreso"]}
        filtro = st.segmented_control("Mostrar", list(filtros), default="Todos", key="filtro_movimientos",
                                      label_visibility="collapsed") or "Todos"
        estilo.lista_movimientos(
            [t for t in tarjetas if filtros[filtro](t)], key="lista_movimientos",
            al_abrir=lambda nombre: st.session_state.update(abrir_comprobante=nombre),
            vacia="No hay movimientos de este tipo.",
        )
    with pestanas[2]:
        faltan = gastos[gastos["Comprobante"] == ""]
        st.markdown("**Gastos sin ticket ni factura**")
        if faltan.empty:
            st.success("Todos los gastos tienen comprobante. 🎉")
        else:
            st.dataframe(faltan, hide_index=True)
        st.markdown("**Comprobantes que no están en el extracto**",
                    help="Pagos en efectivo, de otra tarjeta, de otro mes, o fotos que la IA no ha leído bien.")
        if sueltos.empty:
            st.success("Todos los comprobantes están en el extracto.")
        else:
            tabla_con_comprobantes(sueltos, "Archivo", "tabla_sueltos")
    with pestanas[3]:
        st.caption("Por ejemplo: «¿Cuánto he gastado en restauración?» o «¿Qué gastos no tienen ticket?»")
        turnos = st.session_state.setdefault("conversacion", [])
        if turnos and st.button("🗑️ Borrar la conversación"):
            turnos.clear()
            almacen.guardar_conversacion(activo["id"], [])
        # Como en cualquier chat: las preguntas y respuestas arriba y el campo para escribir siempre debajo
        chat = st.container(height=500)
        pregunta = st.chat_input("Pregunte sobre este cuadre…")
        with chat:
            for turno in turnos:
                mostrar_turno(turno)
            if pregunta:
                with st.chat_message("user"):
                    st.markdown(pregunta)
                modelo = obtener_modelo(st.session_state.get("modelo_elegido", AUTOMATICO))
                if modelo is None:
                    st.error("La app no está bien configurada (falta la clave). Avise a quien la mantiene.")
                else:
                    with st.spinner(f"🤖 Buscando la respuesta con {modelo_principal(modelo)}…"):
                        datos = datos_para_conversar(movimientos, leidos, gastos, sueltos)
                        turno, error = conversar(modelo, pregunta, turnos, gastos, datos)
                    if error:
                        st.error(error)
                    else:
                        turnos.append(turno)
                        almacen.guardar_conversacion(activo["id"], turnos)
                        mostrar_respuesta(turno)

    with pestanas[4]:
        st.caption("Compruebe que los importes y fechas coinciden con sus documentos: la IA puede equivocarse.")
        if leidos:
            st.write("**Comprobantes**")
            st.dataframe(pd.DataFrame(leidos), hide_index=True)
        st.write("**Movimientos del extracto**")
        st.dataframe(pd.DataFrame(movimientos), hide_index=True)

    # Se abre aquí (y no en la tabla) para que no vuelva a salir al mover un ajuste
    nombre = st.session_state.pop("abrir_comprobante", "")
    if nombre:
        ver_comprobante(nombre, archivos, leidos, gastos, activo.get("huellas", {}))

st.caption("La IA puede equivocarse al leer: revise los importes antes de enviarlos. Esta app no sustituye a su gestoría.")

# Al final, para mandar al navegador lo que se haya guardado en esta ejecución
almacen.sincronizar()
