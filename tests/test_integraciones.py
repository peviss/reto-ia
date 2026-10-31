"""Pruebas de integraciones.py y drive.py: qué se envía y cómo se manejan los fallos (F4).

Ninguna prueba sale a internet: las peticiones y la búsqueda de direcciones se sustituyen por otras falsas.
Ejecutar:  python -m unittest discover -s tests -v
"""

import base64
import copy
import io
import json
import socket
import unittest
import urllib.error
from unittest import mock

import drive
import integraciones
from cuadre import cuadrar
from datos_ejemplo import COMPROBANTES, MOVIMIENTOS

def ip_publica(*_args):
    """Imita socket.getaddrinfo para una dirección pública de internet."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]


def ip_privada(*_args):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))]


class Respuesta(io.BytesIO):
    """Lo que devuelve urlopen: se usa con «with» y tiene read()."""


def error_http(codigo):
    return urllib.error.HTTPError("https://falso", codigo, "error", {}, None)


class AbrirFalso:
    """Imita la red: guarda cada petición y responde con lo que se le pase, en orden (o lanza el error)."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []

    def __call__(self, peticion, timeout):
        self.peticiones.append(peticion)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return Respuesta(json.dumps(respuesta).encode() if isinstance(respuesta, dict) else respuesta)


class ConRedFalsa(unittest.TestCase):

    def usar_red(self, *respuestas, resolver=ip_publica):
        abrir = AbrirFalso(*respuestas)
        for parche in (mock.patch.object(integraciones, "abrir", abrir),
                       mock.patch.object(integraciones.socket, "getaddrinfo", side_effect=resolver)):
            parche.start()
            self.addCleanup(parche.stop)
        return abrir


class QueSeEnvia(unittest.TestCase):

    def setUp(self):
        gastos, resumen, sueltos = cuadrar(copy.deepcopy(MOVIMIENTOS), copy.deepcopy(COMPROBANTES))
        self.datos = integraciones.datos_del_cuadre("Octubre", "extracto_octubre.csv", gastos, resumen,
                                                    sueltos, b"excel")

    def test_totales_como_en_la_app(self):
        # Los mismos números que las 4 cifras de arriba (CA1): 10 gastos, 7 con comprobante, 1 suelto
        self.assertEqual(self.datos["totales"]["gastos"], 10)
        self.assertEqual(self.datos["totales"]["con_comprobante"], 7)
        self.assertEqual(self.datos["totales"]["comprobantes_fuera_del_banco"], 1)

    def test_se_puede_pasar_a_json_con_el_excel(self):
        texto = json.dumps(self.datos)  # falla si queda algún número de pandas
        self.assertEqual(json.loads(texto), self.datos)
        self.assertIn("Restauración", [fila["Categoría"] for fila in self.datos["por_categoria"]])
        self.assertEqual(base64.b64decode(self.datos["excel"]["base64"]), b"excel")
        self.assertEqual(self.datos["excel"]["nombre"], "Octubre.xlsx")


class IntegracionPropia(ConRedFalsa):

    def test_envia_el_json_con_la_clave(self):
        red = self.usar_red(b"ok")
        integraciones.enviar_webhook("https://hooks.ejemplo.com/cuadre", {"cuadre": "Octubre"}, " secreta ")
        peticion = red.peticiones[0]
        self.assertEqual(peticion.get_method(), "POST")
        self.assertEqual(json.loads(peticion.data), {"cuadre": "Octubre"})
        self.assertEqual(peticion.get_header("Authorization"), "Bearer secreta")

    def test_sin_clave_no_manda_cabecera(self):
        red = self.usar_red(b"ok")
        integraciones.enviar_webhook("https://hooks.ejemplo.com/cuadre", {})
        self.assertIsNone(red.peticiones[0].get_header("Authorization"))

    def test_solo_https(self):
        red = self.usar_red()
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "https://"):
            integraciones.enviar_webhook("http://hooks.ejemplo.com/cuadre", {})
        self.assertFalse(red.peticiones)

    def test_no_envia_a_la_red_interna(self):
        red = self.usar_red(resolver=ip_privada)
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "no es pública"):
            integraciones.enviar_webhook("https://router.casa/cuadre", {})
        self.assertFalse(red.peticiones)

    def test_direccion_que_no_existe(self):
        self.usar_red(resolver=mock.Mock(side_effect=socket.gaierror("no existe")))
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "No se encuentra"):
            integraciones.enviar_webhook("https://no-existe.ejemplo/cuadre", {})

    def test_redireccion_a_la_red_interna(self):
        self.usar_red(resolver=ip_privada)
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "no es pública"):
            integraciones.RedireccionSegura().redirect_request(None, None, 302, "", {}, "https://10.0.0.1/")

    def test_errores_con_mensaje_claro(self):
        for error, texto in [(error_http(401), "permiso denegado"), (error_http(404), "404"),
                             (error_http(503), "unos minutos"), (urllib.error.URLError("sin red"), "No hay conexión"),
                             (TimeoutError(), "No hay conexión")]:
            with self.subTest(error=error):
                self.usar_red(error)
                with self.assertRaisesRegex(integraciones.ErrorIntegracion, texto):
                    integraciones.enviar_webhook("https://hooks.ejemplo.com/cuadre", {})


class GoogleDrive(unittest.TestCase):
    """Drive se guarda desde el navegador (drive.py): aquí solo se prueba la parte de Python."""

    def test_sale_solo_con_client_id(self):
        with mock.patch.object(drive.st, "secrets", {"google_drive": {"client_id": "id.apps.googleusercontent.com"}}):
            self.assertEqual(drive.client_id(), "id.apps.googleusercontent.com")
        for secretos in ({}, {"google_drive": {"client_id": ""}}, {"google_drive": {}}):
            with self.subTest(secretos=secretos), mock.patch.object(drive.st, "secrets", secretos):
                self.assertIsNone(drive.client_id())

    def test_sin_secretos_de_servidor(self):
        # El flujo OAuth es del navegador: el JavaScript no lleva client_secret ni refresh_token
        self.assertNotIn("client_secret", drive.JS)
        self.assertNotIn("refresh_token", drive.JS)
        self.assertIn("drive.file", drive.JS)  # el permiso más pequeño: solo los archivos que crea la app


if __name__ == "__main__":
    unittest.main()
