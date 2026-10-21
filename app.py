"""Cuadra tus gastos: empareja tickets y facturas con el extracto del banco y los agrupa por categoría.

App Streamlit (Ruta A) con la API de Gemini (capa gratuita).
- La IA (Gemini) LEE: saca los movimientos del extracto y los datos de cada ticket o factura.
- Python CUADRA: empareja por importe y fecha y agrupa por categoría (cuadre.py).
La clave se lee de los secretos de la plataforma: nunca se escribe en el código.
"""

import io
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from google import genai
from google.genai import errors, types
from PIL import Image, ImageOps
from pydantic import BaseModel

from cuadre import CATEGORIAS, cuadrar

MODELO = "gemini-2.5-flash"
MAX_COMPROBANTES = 20
COMPROBANTES_POR_LLAMADA = 5
MAX_MB_ARCHIVO = 8
MAX_LINEAS_EXTRACTO = 300
CARPETA_EJEMPLOS = Path(__file__).parent / "ejemplos"

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
    total: float
    categoria: str
    legible: bool


LISTA_CATEGORIAS = ", ".join(CATEGORIAS)

PROMPT_EXTRACTO = f"""Eres un asistente contable. Te paso un extracto bancario español \
(CSV, Excel convertido a texto o PDF). Devuelve TODOS los movimientos, sin saltarte ninguno.

Reglas:
- fecha: la fecha de operación en formato AAAA-MM-DD.
- concepto: el texto del concepto tal cual aparece.
- importe: número con punto decimal. Gastos y cargos en NEGATIVO, ingresos en POSITIVO. \
Si el extracto tiene columnas separadas de cargo y abono, aplica el signo tú.
- categoria: elige UNA de esta lista, exactamente escrita así: {LISTA_CATEGORIAS}.
- No inventes movimientos. No incluyas la fila de saldo inicial o final.
"""

PROMPT_COMPROBANTES = f"""Eres un asistente contable. Te paso fotos de tickets y facturas \
(imágenes o PDF). Cada uno va precedido de su nombre de archivo. Devuelve un elemento por archivo.

Reglas:
- archivo: el nombre de archivo exacto que te indico.
- comercio: nombre del comercio o empresa que emite el documento.
- fecha: fecha de la compra o de la factura en formato AAAA-MM-DD; "" si no se lee.
- total: el TOTAL pagado, IVA incluido, número con punto decimal. No uses subtotales ni la \
cantidad entregada en efectivo.
- categoria: elige UNA de esta lista, exactamente escrita así: {LISTA_CATEGORIAS}.
- legible: false si no es un ticket o factura o no se puede leer el total (entonces total = 0).
- No inventes datos: si dudas de un número, marca legible = false.
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
    except Exception:  # p. ej. HEIC: Gemini lo lee directamente
        return archivo


def contenido_extracto(archivo):
    """Prepara el extracto para la IA: texto si es CSV/Excel, el PDF tal cual si es PDF."""
    if archivo["mime"] == "application/pdf":
        return types.Part.from_bytes(data=archivo["datos"], mime_type="application/pdf")
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

def obtener_cliente():
    """Crea el cliente de Gemini con la clave de los secretos. Devuelve None si falta."""
    try:
        clave = st.secrets["GEMINI_API_KEY"]
    except Exception:  # sin secrets.toml o sin la clave
        return None
    return genai.Client(api_key=clave)


def mensaje_error(e):
    """Traduce un error de la API a un mensaje que entiende cualquier persona."""
    if e.code == 429:
        return "Se ha agotado la cuota gratuita de la IA por ahora. Espere un minuto (o vuelva mañana si persiste) y pruebe de nuevo."
    if e.code in (401, 403) or (e.code == 400 and "API key" in str(e)):
        return "La app no está bien configurada (clave no válida). Avise a quien la mantiene."
    if e.code == 400:
        return "La IA no ha podido abrir alguno de los archivos. Compruebe que no están dañados ni protegidos con contraseña."
    if e.code and e.code >= 500:
        return "El servicio de IA no responde en este momento. Pruebe de nuevo en unos minutos."
    return "No se han podido procesar los archivos. Pruebe de nuevo."


def llamar_gemini(cliente, contenido, prompt, esquema):
    """Llama a Gemini pidiendo JSON con el esquema dado. Reintenta una vez si se agota la cuota.

    Devuelve (lista_de_dicts, mensaje_de_error).
    """
    config = types.GenerateContentConfig(
        system_instruction=prompt,
        temperature=0,
        response_mime_type="application/json",
        response_schema=list[esquema],
    )
    for intento in range(2):
        try:
            respuesta = cliente.models.generate_content(model=MODELO, contents=contenido, config=config)
            break
        except errors.APIError as e:
            if e.code == 429 and intento == 0:
                st.info("Hay muchas consultas. Esperando 30 segundos para reintentar…")
                time.sleep(30)
                continue
            return None, mensaje_error(e)
        except Exception:
            return None, "No hay conexión con el servicio de IA. Pruebe de nuevo en unos minutos."

    if not respuesta.parsed:
        return None, "La IA no ha devuelto datos para estos archivos. Pruebe con otros o con fotos más nítidas."
    return [elemento.model_dump() for elemento in respuesta.parsed], None


def leer_extracto(cliente, archivo):
    try:
        contenido = contenido_extracto(archivo)
    except ValueError as e:
        return None, str(e)
    except Exception:
        return None, "No se ha podido abrir el extracto. Descárguelo de nuevo del banco en CSV, Excel o PDF."
    return llamar_gemini(cliente, contenido, PROMPT_EXTRACTO, Movimiento)


def leer_comprobantes(cliente, archivos, barra):
    """Lee los comprobantes por lotes para no pasarse de la cuota por minuto."""
    leidos = []
    for inicio in range(0, len(archivos), COMPROBANTES_POR_LLAMADA):
        lote = [reducir_imagen(a) for a in archivos[inicio:inicio + COMPROBANTES_POR_LLAMADA]]
        contenido = []
        for archivo in lote:
            contenido.append(f"Archivo: {archivo['nombre']}")
            contenido.append(types.Part.from_bytes(data=archivo["datos"], mime_type=archivo["mime"]))
        datos, error = llamar_gemini(cliente, contenido, PROMPT_COMPROBANTES, Comprobante)
        if error:
            return None, error
        leidos.extend(datos)
        barra.progress(min(1.0, (inicio + len(lote)) / len(archivos)), text=f"Leyendo comprobantes… {inicio + len(lote)} de {len(archivos)}")

    # Si la IA se ha saltado algún archivo, lo añadimos como no legible para que el usuario lo vea
    nombres_leidos = {c["archivo"] for c in leidos}
    for archivo in archivos:
        if archivo["nombre"] not in nombres_leidos:
            leidos.append({"archivo": archivo["nombre"], "comercio": "", "fecha": "", "total": 0.0, "categoria": "Otros", "legible": False})
    return leidos, None


def validar(extracto, comprobantes):
    """Comprueba la entrada antes de gastar cuota. Devuelve un aviso o None."""
    if extracto is None:
        return "Falta el extracto del banco. Súbalo en el paso 1 o pulse «Probar con datos de ejemplo»."
    if not comprobantes:
        return "Faltan los tickets o facturas. Súbalos en el paso 2."
    if len(comprobantes) > MAX_COMPROBANTES:
        return f"Ha subido {len(comprobantes)} comprobantes. El máximo es {MAX_COMPROBANTES} cada vez: hágalo por partes (por ejemplo, por semanas)."
    for archivo in [extracto, *comprobantes]:
        if len(archivo["datos"]) > MAX_MB_ARCHIVO * 1024 * 1024:
            return f"El archivo «{archivo['nombre']}» pesa más de {MAX_MB_ARCHIVO} MB. Haga la foto de nuevo o reduzca el PDF."
    return None


def a_excel(gastos, resumen, sueltos):
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as excel:
        resumen.to_excel(excel, sheet_name="Por categoría", index=False)
        gastos.to_excel(excel, sheet_name="Gastos", index=False)
        sueltos.to_excel(excel, sheet_name="Comprobantes sueltos", index=False)
    return salida.getvalue()


# ---------- Interfaz ----------

st.set_page_config(page_title="Cuadra tus gastos", page_icon="🧾", layout="wide")

st.title("🧾 Cuadra tus gastos")
st.markdown(
    "Suba el **extracto de su banco** y las **fotos de sus tickets o facturas**. "
    "La app le dice **qué gasto corresponde a cada ticket**, **qué gastos no tienen justificante** "
    "y **cuánto ha gastado en cada categoría**, listo para enviar a su gestoría."
)

with st.expander("ℹ️ Cómo se usa y qué pasa con mis datos"):
    st.markdown(
        "1. **Extracto:** en la web de su banco, descargue los movimientos del mes en CSV, Excel o PDF.\n"
        "2. **Comprobantes:** haga una foto a cada ticket (que se vea el total y la fecha) o suba la factura en PDF.\n"
        "3. Pulse **Cuadrar gastos** y espere unos segundos.\n"
        "4. Revise el resultado y descárguelo en Excel.\n\n"
        "**Cómo empareja:** un ticket y un gasto van juntos si tienen **el mismo importe** y las fechas "
        "se separan pocos días (los pagos con tarjeta pueden tardar 1–3 días en aparecer en el banco). "
        "Si alguien adelantó varias compras y luego se le **reembolsó el total** con una transferencia, "
        "la app busca los tickets anteriores que **suman** ese importe.\n\n"
        "⚠️ **Privacidad:** los archivos se envían a la IA de Google (Gemini) para leerlos. "
        "En la versión gratuita, Google puede usarlos para mejorar sus servicios. "
        "**Para probar, use los datos de ejemplo**; con datos reales, tape antes el número de cuenta y su DNI."
    )

if st.button("🧪 Probar con datos de ejemplo (inventados)"):
    st.session_state.ejemplo = True
    st.session_state.pop("resultado", None)

usar_ejemplo = st.session_state.get("ejemplo", False)

col1, col2 = st.columns(2)
with col1:
    subido_extracto = st.file_uploader("**Paso 1.** Extracto del banco", type=["csv", "xlsx", "pdf"])
with col2:
    subidos_comprobantes = st.file_uploader(
        "**Paso 2.** Tickets y facturas",
        type=["jpg", "jpeg", "png", "webp", "heic", "pdf"],
        accept_multiple_files=True,
    )

if subido_extracto or subidos_comprobantes:
    usar_ejemplo = st.session_state.ejemplo = False  # lo que sube el usuario manda sobre el ejemplo

if usar_ejemplo:
    extracto, comprobantes = cargar_ejemplos()
    st.info(f"Usando datos de ejemplo: «{extracto['nombre']}» y {len(comprobantes)} comprobantes inventados.")
else:
    extracto = archivo_desde_subida(subido_extracto) if subido_extracto else None
    comprobantes = [archivo_desde_subida(a) for a in subidos_comprobantes or []]

with st.expander("⚙️ Ajustes"):
    tolerancia = st.slider(
        "Días de diferencia permitidos entre el ticket y el banco", 0, 10, 4,
        help="Un pago con tarjeta del viernes puede aparecer en el banco el lunes.",
    )
    ventana_reembolso = st.slider(
        "Reembolsos: buscar tickets de hasta cuántos días antes del pago", 0, 90, 30,
        help="Cuando alguien adelanta varias compras y luego se le transfiere el total, "
        "la app busca tickets anteriores al pago que sumen ese importe. 0 = no buscar.",
    )

if st.button("Cuadrar gastos", type="primary"):
    aviso = validar(extracto, comprobantes)
    cliente = None if aviso else obtener_cliente()
    if aviso:
        st.warning(aviso)
    elif cliente is None:
        st.error("La app no está bien configurada (falta la clave). Avise a quien la mantiene.")
    else:
        barra = st.progress(0.0, text="Leyendo el extracto del banco…")
        movimientos, error = leer_extracto(cliente, extracto)
        if not error and not any(m["importe"] < 0 for m in movimientos):
            error = "No se ha encontrado ningún gasto en el extracto. Compruebe que ha subido el archivo correcto."
        if not error:
            leidos, error = leer_comprobantes(cliente, comprobantes, barra)
        barra.empty()
        if error:
            st.error(error)
        else:
            st.session_state.resultado = (movimientos, leidos)

# El resultado se guarda para poder mover el ajuste de días sin volver a llamar a la IA
if "resultado" in st.session_state:
    movimientos, leidos = st.session_state.resultado
    gastos, resumen, sueltos = cuadrar(movimientos, leidos, tolerancia, ventana_reembolso)

    # Un reembolso agrupado ocupa varias filas: contamos movimientos por su n.º («Mov.»)
    con = gastos["Comprobante"] != ""
    total = gastos["Importe (€)"].sum()
    justificado = gastos.loc[con, "Importe (€)"].sum()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Gastos en el extracto", f"{gastos['Mov.'].nunique()}", f"{total:,.2f} €", delta_color="off")
    m2.metric("Con comprobante", f"{gastos.loc[con, 'Mov.'].nunique()}", f"{justificado:,.2f} €", delta_color="off")
    m3.metric("Sin comprobante", f"{gastos.loc[~con, 'Mov.'].nunique()}", f"{total - justificado:,.2f} €", delta_color="off")
    m4.metric("Comprobantes que no están en el banco", f"{len(sueltos)}")

    revisar = gastos[gastos["Estado"].str.contains("revisar")]
    if not revisar.empty:
        st.warning(
            "Algún reembolso agrupado se puede formar con más de una combinación de tickets. "
            "Revise las filas marcadas con «revisar» en *Todos los gastos*."
        )

    pestanas = st.tabs(["📊 Por categoría", "📋 Todos los gastos", "⚠️ Qué falta", "🔍 Lo que ha leído la IA"])
    with pestanas[0]:
        st.dataframe(resumen, hide_index=True)
        if not resumen.empty:
            st.bar_chart(resumen, x="Categoría", y="Total (€)", horizontal=True)
    with pestanas[1]:
        st.caption("🔗 = varios tickets justifican un solo pago (por ejemplo, una transferencia de reembolso). Comparten n.º de «Mov.».")
        st.dataframe(gastos, hide_index=True)
    with pestanas[2]:
        faltan = gastos[gastos["Comprobante"] == ""]
        st.subheader("Gastos del banco sin ticket ni factura")
        if faltan.empty:
            st.success("Todos los gastos tienen comprobante. 🎉")
        else:
            st.caption("Busque estos justificantes o pídalos al comercio.")
            st.dataframe(faltan, hide_index=True)
        st.subheader("Comprobantes que no aparecen en el extracto")
        if sueltos.empty:
            st.success("Todos los comprobantes están en el extracto.")
        else:
            st.caption("Pueden ser pagos en efectivo, de otra tarjeta, de otro mes, o fotos que la IA no ha leído bien.")
            st.dataframe(sueltos, hide_index=True)
    with pestanas[3]:
        st.caption("Compruebe que los importes y fechas coinciden con sus documentos: la IA puede equivocarse.")
        st.write("**Comprobantes**")
        st.dataframe(pd.DataFrame(leidos), hide_index=True)
        st.write("**Movimientos del extracto**")
        st.dataframe(pd.DataFrame(movimientos), hide_index=True)

    st.download_button(
        "⬇️ Descargar en Excel (para la gestoría)",
        data=a_excel(gastos, resumen, sueltos),
        file_name="gastos_cuadrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.divider()
st.caption(
    "La lectura de tickets y extractos la hace una inteligencia artificial y puede contener errores. "
    "Revise siempre los importes antes de enviarlos. Esta app no sustituye a su gestoría."
)
