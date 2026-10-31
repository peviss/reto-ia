"""Integraciones: envía el cuadre abierto a un servicio externo desde el servidor (F4).

Python puro (sin Streamlit ni IA) y solo con la biblioteca estándar, para poder probarlo sin red.

- **Integración propia (webhook)**: manda el cuadre en JSON, con un POST, a la dirección que ponga el
  usuario: Make, Zapier, n8n, un Apps Script o la API de su programa de contabilidad.

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
        raise ErrorIntegracion(f"{servicio} ha rechazado el envío (error {e.code}).") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise ErrorIntegracion(f"No hay conexión con {servicio}. Pruebe de nuevo en unos minutos.") from None


# ---------- Integración propia (webhook) ----------

def enviar_webhook(url, datos, clave=""):
    """POST con el cuadre en JSON. La clave, si la hay, va en la cabecera «Authorization: Bearer …»."""
    comprobar_direccion(url)
    cabeceras = {"Content-Type": "application/json; charset=utf-8", "User-Agent": "cuadra-tus-gastos"}
    if clave.strip():
        cabeceras["Authorization"] = f"Bearer {clave.strip()}"
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    pedir(urllib.request.Request(url.strip(), data=cuerpo, headers=cabeceras, method="POST"), "El servicio")

