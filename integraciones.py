"""Integraciones: envía el cuadre abierto a un servicio externo desde el servidor (F3).

Python puro (sin Streamlit ni IA) y solo con la biblioteca estándar, para poder probarlo sin red.

- **Integración propia**: manda el cuadre en JSON a la dirección que configure el usuario: Make, Zapier,
  n8n, un Apps Script o la API de su programa de contabilidad. La configuración dice cómo:
  todo el cuadre con el formato de la app, o los gastos con los **campos** que pide esa API
  (cada campo: su nombre en la API, de dónde sale el valor y en qué formato). La puede escribir el
  usuario a mano o proponerla la IA leyendo la especificación de la API (app.py), pero envía Python.

Google Drive no va aquí: se guarda desde el navegador del usuario, con su cuenta de Google (drive.py).
Para añadir otro destino: una función `enviar_a_…` que lance `ErrorIntegracion` con un mensaje claro si falla.
"""

import base64
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

MIME_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SEGUNDOS_ESPERA = 20  # si el servicio tarda más, se da por caído
VERSION_FORMATO = 1  # sube si cambia la forma del JSON del webhook, para que el receptor lo sepa
MAX_KB_ESPECIFICACION = 2048  # una especificación descargada más grande no se lee

# Cómo se envía: todo el cuadre en una petición con el formato de la app, o los gastos con sus campos
ENVIOS = {
    "completo": "Todo el cuadre (formato de la app)",
    "lista": "Una petición con la lista de gastos",
    "uno_por_gasto": "Una petición por gasto",
}
METODOS = ("POST", "PUT", "PATCH")
AUTENTICACIONES = {
    "ninguna": "Sin clave",
    "bearer": "Authorization: Bearer <clave>",
    "cabecera": "Cabecera propia con la clave (p. ej. X-API-Key)",
}
# De dónde sale el valor de cada campo: un dato de cada gasto, el nombre del cuadre o un valor fijo
ORIGENES = {
    "fecha": "Fecha del gasto (AAAA-MM-DD)",
    "importe": "Importe en € (positivo)",
    "concepto": "Concepto del banco",
    "categoria": "Categoría",
    "comercio": "Comercio del ticket o factura",
    "comprobante": "Nombre del archivo del comprobante",
    "justificado": "Tiene comprobante (sí / no)",
    "estado": "Estado del emparejamiento",
    "movimiento": "N.º de movimiento",
    "cuadre": "Nombre del cuadre",
    "fijo": "Valor fijo (el que escriba)",
}
FORMATOS = {
    "tal_cual": "Tal cual",
    "texto": "Texto",
    "numero": "Número",
    "negativo": "Número en negativo",
    "centimos": "Céntimos (número entero)",
    "fecha_dma": "Fecha DD/MM/AAAA",
    "fecha_unix": "Fecha en segundos (Unix)",
}


class ErrorIntegracion(Exception):
    """Un fallo al enviar, con un mensaje que entiende cualquier persona."""


# ---------- Qué se envía ----------

def tabla_a_lista(tabla):
    """DataFrame → lista de dicts con tipos de JSON (los números de pandas no se pueden pasar a JSON tal cual)."""
    return json.loads(tabla.to_json(orient="records", force_ascii=False))


def datos_del_cuadre(nombre, extracto, gastos, resumen, sueltos, excel):
    """Todo el cuadre en un dict que se puede pasar a JSON: totales, tablas y el Excel en base64."""
    con = gastos["Comprobante"] != ""
    return {
        "app": "cuadra-tus-gastos",
        "version": VERSION_FORMATO,
        "enviado": datetime.now().isoformat(timespec="seconds"),
        "cuadre": nombre,
        "extracto": extracto,
        "totales": {  # un reembolso agrupado son varias filas con el mismo «Mov.»: se cuenta una vez
            "gastos": int(gastos["Mov."].nunique()),
            "importe": round(float(gastos["Importe (€)"].sum()), 2),
            "con_comprobante": int(gastos.loc[con, "Mov."].nunique()),
            "sin_comprobante_importe": round(float(gastos.loc[~con, "Importe (€)"].sum()), 2),
            "comprobantes_fuera_del_banco": len(sueltos),
        },
        "por_categoria": tabla_a_lista(resumen),
        "gastos": tabla_a_lista(gastos),
        "comprobantes_sueltos": tabla_a_lista(sueltos),
        "excel": {"nombre": f"{nombre}.xlsx", "mime": MIME_EXCEL, "base64": base64.b64encode(excel).decode()},
    }


# ---------- Peticiones HTTP ----------

def comprobar_direccion(url):
    """Solo se envía a direcciones https públicas de internet.

    Así nadie puede usar la app (que corre en un servidor) para llegar a máquinas de su red interna.
    """
    partes = urllib.parse.urlsplit(url.strip())
    if partes.scheme != "https" or not partes.hostname:
        raise ErrorIntegracion("La dirección debe empezar por «https://». Cópiela entera de su servicio.")
    try:
        direcciones = {info[4][0] for info in socket.getaddrinfo(partes.hostname, partes.port or 443)}
    except (socket.gaierror, UnicodeError):
        raise ErrorIntegracion("No se encuentra esa dirección. Compruebe que está bien escrita.") from None
    if not all(ipaddress.ip_address(ip.split("%")[0]).is_global for ip in direcciones):
        raise ErrorIntegracion("Esa dirección no es pública: solo se puede enviar a servicios de internet.")


class RedireccionSegura(urllib.request.HTTPRedirectHandler):
    """Sigue las redirecciones (Apps Script las usa) solo si van a otra dirección pública."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        comprobar_direccion(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


abrir = urllib.request.build_opener(RedireccionSegura()).open  # las pruebas lo sustituyen por uno falso


def pedir(peticion, servicio):
    """Hace la petición y devuelve el cuerpo de la respuesta. Traduce los fallos a un mensaje claro."""
    try:
        with abrir(peticion, timeout=SEGUNDOS_ESPERA) as respuesta:
            return respuesta.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ErrorIntegracion(f"{servicio} no acepta el envío (permiso denegado). Revise la clave o los permisos.") from None
        if e.code == 404:
            raise ErrorIntegracion(f"{servicio} no encuentra el destino (error 404). Revise la dirección.") from None
        if e.code == 413:
            raise ErrorIntegracion(f"{servicio} no acepta envíos tan grandes.") from None
        if e.code >= 500:
            raise ErrorIntegracion(f"{servicio} no responde en este momento. Pruebe de nuevo en unos minutos.") from None
        if e.code in (400, 422):  # los datos no son los que espera: su explicación ayuda a corregir los campos
            detalle = (e.read() or b"")[:300].decode("utf-8", errors="replace").strip()
            raise ErrorIntegracion(f"{servicio} ha rechazado los datos (error {e.code}). Revise los campos de la "
                                   f"integración." + (f" Respuesta: {detalle}" if detalle else "")) from None
        raise ErrorIntegracion(f"{servicio} ha rechazado el envío (error {e.code}).") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise ErrorIntegracion(f"No hay conexión con {servicio}. Pruebe de nuevo en unos minutos.") from None


# ---------- Integración propia: configuración y campos ----------

def configuracion_nueva():
    """Una integración vacía: envía todo el cuadre, sin clave."""
    return {"id": "", "nombre": "", "url": "", "metodo": "POST", "autenticacion": "ninguna",
            "cabecera_clave": "", "envio": "completo", "campo_lista": "", "campos": [], "notas": ""}


def validar_configuracion(config):
    """Comprueba una integración antes de guardarla o enviarla. Devuelve un aviso o None."""
    if not config["nombre"].strip():
        return "Ponga un nombre a la integración (por ejemplo, el de su programa de contabilidad)."
    if not config["url"].strip().startswith("https://"):
        return "La dirección debe empezar por «https://». Cópiela entera de su servicio."
    if config["metodo"] not in METODOS or config["envio"] not in ENVIOS or config["autenticacion"] not in AUTENTICACIONES:
        return "Falta elegir el método, cómo se envía o la clave."
    if config["autenticacion"] == "cabecera" and not config["cabecera_clave"].strip():
        return "Escriba el nombre de la cabecera que lleva la clave (por ejemplo, X-API-Key)."
    if config["envio"] == "completo":
        return None
    if not config["campos"]:
        return "Añada al menos un campo: qué dato de cada gasto va en qué campo de la API."
    destinos = [c["destino"].strip() for c in config["campos"]]
    if any(not d for d in destinos):
        return "Hay un campo sin nombre en la API. Escríbalo o borre la fila."
    if len(set(destinos)) < len(destinos):
        return "Hay dos campos con el mismo nombre en la API."
    for campo in config["campos"]:
        if campo["origen"] not in ORIGENES or campo["formato"] not in FORMATOS:
            return f"Elija de dónde sale y en qué formato va el campo «{campo['destino']}»."
    return None


def filas_para_enviar(gastos, leidos, nombre_cuadre):
    """Cada gasto del cuadre con los datos que se pueden mandar (las claves de ORIGENES).

    Un reembolso agrupado son varias filas con el mismo n.º de movimiento: cada compra va con su categoría.
    """
    comercios = {c["archivo"]: c.get("comercio", "") for c in leidos}
    return [{
        "fecha": str(fila["Fecha"]), "importe": round(float(fila["Importe (€)"]), 2),
        "concepto": fila["Concepto"], "categoria": fila["Categoría"],
        "comercio": comercios.get(fila["Comprobante"], ""), "comprobante": fila["Comprobante"],
        "justificado": bool(fila["Comprobante"]), "estado": fila["Estado"], "movimiento": int(fila["Mov."]),
        "cuadre": nombre_cuadre,
    } for _, fila in gastos.iterrows()]


def dar_formato(valor, formato):
    """Convierte un valor al formato que pide la API. Si no se puede (p. ej. una fecha vacía), lo deja igual."""
    try:
        if formato == "texto":
            return str(valor)
        if formato == "numero":
            return float(valor)
        if formato == "negativo":
            return -abs(float(valor))
        if formato == "centimos":
            return int(round(float(valor) * 100))
        if formato == "fecha_dma":
            return datetime.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
        if formato == "fecha_unix":
            return int(datetime.fromisoformat(str(valor)[:10]).timestamp())
    except (TypeError, ValueError):
        pass
    return valor


def poner(destino, ruta, valor):
    """Escribe el valor en la ruta: «contact.name» crea {"contact": {"name": …}}; «lines.0.price», una lista."""
    partes = ruta.strip().split(".")
    actual = destino
    for parte, siguiente in zip(partes, partes[1:]):
        hueco = [] if siguiente.isdigit() else {}
        if isinstance(actual, list):
            indice = int(parte)
            actual.extend([None] * (indice + 1 - len(actual)))
            actual[indice] = actual[indice] if actual[indice] is not None else hueco
            actual = actual[indice]
        else:
            actual = actual.setdefault(parte, hueco)
    if isinstance(actual, list):
        indice = int(partes[-1])
        actual.extend([None] * (indice + 1 - len(actual)))
        actual[indice] = valor
    else:
        actual[partes[-1]] = valor


def cuerpo_de_gasto(campos, fila):
    """El JSON de un gasto con los campos de la integración."""
    cuerpo = {}
    for campo in campos:
        valor = campo.get("valor", "") if campo["origen"] == "fijo" else fila[campo["origen"]]
        poner(cuerpo, campo["destino"], dar_formato(valor, campo["formato"]))
    return cuerpo


def cuerpos(config, filas, datos_completos):
    """Lo que se manda en cada petición, según cómo se envía."""
    if config["envio"] == "completo":
        return [datos_completos]
    por_gasto = [cuerpo_de_gasto(config["campos"], fila) for fila in filas]
    if config["envio"] == "uno_por_gasto":
        return por_gasto
    lista = config["campo_lista"].strip()
    return [poner_lista(lista, por_gasto) if lista else por_gasto]


def poner_lista(ruta, lista):
    cuerpo = {}
    poner(cuerpo, ruta, lista)
    return cuerpo


def cabeceras(config, clave):
    """Las cabeceras de cada petición: JSON y, si la hay, la clave donde diga la configuración."""
    resultado = {"Content-Type": "application/json; charset=utf-8", "User-Agent": "cuadra-tus-gastos"}
    clave = clave.strip()
    if config["autenticacion"] != "ninguna" and not clave:
        raise ErrorIntegracion("Esta integración necesita una clave. Escríbala antes de enviar.")
    if config["autenticacion"] == "bearer":
        resultado["Authorization"] = f"Bearer {clave}"
    elif config["autenticacion"] == "cabecera":
        resultado[config["cabecera_clave"].strip()] = clave
    return resultado


def enviar(config, clave, filas, datos_completos):
    """Manda el cuadre con la configuración dada. Devuelve cuántas peticiones se han hecho.

    Si una petición falla, se para y el mensaje dice cuántas se habían enviado ya.
    """
    aviso = validar_configuracion(config)
    if aviso:
        raise ErrorIntegracion(aviso)
    encabezados = cabeceras(config, clave)  # antes de salir a la red: si falta la clave, se dice ya
    comprobar_direccion(config["url"])
    lista = cuerpos(config, filas, datos_completos)
    if not lista or lista == [[]]:
        raise ErrorIntegracion("No hay gastos que enviar en este cuadre.")
    nombre = config["nombre"].strip()
    for hechas, cuerpo in enumerate(lista):
        peticion = urllib.request.Request(
            config["url"].strip(), data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
            headers=encabezados, method=config["metodo"])
        try:
            pedir(peticion, nombre)
        except ErrorIntegracion as e:
            if hechas:
                raise ErrorIntegracion(f"Se han enviado {hechas} de {len(lista)} gastos. {e}") from None
            raise
    return len(lista)


def enviar_webhook(url, datos, clave=""):
    """Atajo: POST con todo el cuadre en JSON y la clave, si la hay, como «Authorization: Bearer …»."""
    config = {**configuracion_nueva(), "nombre": "El servicio", "url": url,
              "autenticacion": "bearer" if clave.strip() else "ninguna"}
    return enviar(config, clave, [], datos)


def descargar_especificacion(url):
    """Descarga la especificación de una API (p. ej. un openapi.json) para que la lea el asistente."""
    comprobar_direccion(url)
    datos = pedir(urllib.request.Request(url.strip(), headers={"User-Agent": "cuadra-tus-gastos"}), "Esa dirección")
    if len(datos) > MAX_KB_ESPECIFICACION * 1024:
        raise ErrorIntegracion(f"La especificación pesa más de {MAX_KB_ESPECIFICACION // 1024} MB. "
                               "Pegue solo la parte de la API que quiere usar.")
    return datos.decode("utf-8", errors="replace")
