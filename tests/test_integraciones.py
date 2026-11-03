"""Pruebas de integraciones.py: qué se envía y cómo se manejan los fallos (F3).

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


class CamposDeLaIntegracion(unittest.TestCase):
    """CA30: qué dato del gasto va en qué campo de la API y en qué formato."""

    def setUp(self):
        gastos, _, _ = cuadrar(copy.deepcopy(MOVIMIENTOS), copy.deepcopy(COMPROBANTES))
        self.filas = integraciones.filas_para_enviar(gastos, COMPROBANTES, "Octubre")
        self.config = {**integraciones.configuracion_nueva(), "nombre": "Contabilidad",
                       "url": "https://api.ejemplo.com/gastos", "envio": "uno_por_gasto", "campos": [
                           {"destino": "date", "origen": "fecha", "formato": "fecha_dma", "valor": ""},
                           {"destino": "amount.cents", "origen": "importe", "formato": "centimos", "valor": ""},
                           {"destino": "lines.0.description", "origen": "comercio", "formato": "texto", "valor": ""},
                           {"destino": "account", "origen": "fijo", "formato": "tal_cual", "valor": "629"},
                       ]}

    def fila(self, texto):
        return next(f for f in self.filas if texto in f["concepto"])

    def test_filas_con_los_datos_del_gasto(self):
        self.assertEqual(len(self.filas), 12)  # 10 gastos, y el reembolso agrupado son 3 filas
        gasolinera = self.fila("GASOLINERA")
        self.assertEqual((gasolinera["importe"], gasolinera["justificado"], gasolinera["cuadre"]), (60.0, True, "Octubre"))
        self.assertTrue(gasolinera["comercio"])  # el del ticket leído
        self.assertFalse(self.fila("AUTONOMOS")["justificado"])

    def test_formatos(self):
        casos = [("2026-10-05", "fecha_dma", "05/10/2026"), (12.8, "negativo", -12.8), (-12.8, "negativo", -12.8),
                 (12.8, "centimos", 1280), ("3", "numero", 3.0), (5, "texto", "5"), ("", "fecha_dma", ""),
                 ("2026-10-05", "tal_cual", "2026-10-05")]
        for valor, formato, esperado in casos:
            with self.subTest(formato=formato, valor=valor):
                self.assertEqual(integraciones.dar_formato(valor, formato), esperado)
        self.assertIsInstance(integraciones.dar_formato("2026-10-05", "fecha_unix"), int)

    def test_campos_anidados_y_listas(self):
        cuerpo = integraciones.cuerpo_de_gasto(self.config["campos"], self.fila("GASOLINERA"))
        self.assertEqual(cuerpo["date"], "06/10/2026")
        self.assertEqual(cuerpo["amount"], {"cents": 6000})
        self.assertEqual(list(cuerpo["lines"][0]), ["description"])
        self.assertEqual(cuerpo["account"], "629")

    def test_tres_formas_de_enviar(self):
        completo = integraciones.cuerpos({**self.config, "envio": "completo"}, self.filas, {"cuadre": "Octubre"})
        self.assertEqual(completo, [{"cuadre": "Octubre"}])
        self.assertEqual(len(integraciones.cuerpos(self.config, self.filas, {})), 12)
        lista = integraciones.cuerpos({**self.config, "envio": "lista", "campo_lista": "data.expenses"}, self.filas, {})
        self.assertEqual(len(lista), 1)
        self.assertEqual(len(lista[0]["data"]["expenses"]), 12)
        sin_campo = integraciones.cuerpos({**self.config, "envio": "lista"}, self.filas, {})
        self.assertIsInstance(sin_campo[0], list)

    def test_validar_configuracion(self):
        self.assertIsNone(integraciones.validar_configuracion(self.config))
        malos = [({"nombre": " "}, "nombre"), ({"url": "http://x"}, "https://"), ({"campos": []}, "al menos un campo"),
                 ({"autenticacion": "cabecera"}, "cabecera"),
                 ({"campos": self.config["campos"] + [dict(self.config["campos"][0])]}, "mismo nombre"),
                 ({"campos": [{**self.config["campos"][0], "destino": ""}]}, "sin nombre"),
                 ({"campos": [{**self.config["campos"][0], "origen": "otro"}]}, "de dónde sale")]
        for cambio, texto in malos:
            with self.subTest(cambio=cambio):
                self.assertIn(texto, integraciones.validar_configuracion({**self.config, **cambio}))
        # Todo el cuadre no necesita campos
        self.assertIsNone(integraciones.validar_configuracion({**self.config, "envio": "completo", "campos": []}))

    def test_clave_donde_diga_la_configuracion(self):
        self.assertEqual(integraciones.cabeceras({**self.config, "autenticacion": "bearer"}, " k ")["Authorization"], "Bearer k")
        propia = integraciones.cabeceras({**self.config, "autenticacion": "cabecera", "cabecera_clave": "X-API-Key"}, "k")
        self.assertEqual(propia["X-API-Key"], "k")
        self.assertNotIn("Authorization", integraciones.cabeceras(self.config, "k"))
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "necesita una clave"):
            integraciones.cabeceras({**self.config, "autenticacion": "bearer"}, "")


class EnviarConCampos(ConRedFalsa):

    def setUp(self):
        self.config = {**integraciones.configuracion_nueva(), "nombre": "Contabilidad", "metodo": "PUT",
                       "url": "https://api.ejemplo.com/gastos", "envio": "uno_por_gasto",
                       "campos": [{"destino": "amount", "origen": "importe", "formato": "tal_cual", "valor": ""}]}
        self.filas = [{"importe": 10.0}, {"importe": 20.0}, {"importe": 30.0}]

    def test_CA30_una_peticion_por_gasto(self):
        red = self.usar_red(b"{}", b"{}", b"{}")
        self.assertEqual(integraciones.enviar(self.config, "", self.filas, {}), 3)
        self.assertEqual([json.loads(p.data) for p in red.peticiones], [{"amount": 10.0}, {"amount": 20.0}, {"amount": 30.0}])
        self.assertEqual(red.peticiones[0].get_method(), "PUT")

    def test_si_falla_a_mitad_dice_cuantos_se_enviaron(self):
        self.usar_red(b"{}", error_http(503))
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "Se han enviado 1 de 3 gastos"):
            integraciones.enviar(self.config, "", self.filas, {})

    def test_datos_rechazados_con_la_explicacion_de_la_api(self):
        error = urllib.error.HTTPError("https://falso", 422, "error", {}, io.BytesIO(b'{"error": "amount must be integer"}'))
        self.usar_red(error)
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "Revise los campos.*amount must be integer"):
            integraciones.enviar(self.config, "", self.filas, {})

    def test_sin_gastos(self):
        self.usar_red()
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "No hay gastos"):
            integraciones.enviar({**self.config, "envio": "lista"}, "", [], {})

    def test_sin_clave_avisa_antes_de_salir_a_la_red(self):
        resolver = mock.Mock(side_effect=ip_publica)
        self.usar_red(resolver=resolver)
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "necesita una clave"):
            integraciones.enviar({**self.config, "autenticacion": "bearer"}, " ", self.filas, {})
        resolver.assert_not_called()

    def test_configuracion_mal_no_envia(self):
        red = self.usar_red()
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "nombre"):
            integraciones.enviar({**self.config, "nombre": ""}, "", self.filas, {})
        self.assertFalse(red.peticiones)


class DescargarEspecificacion(ConRedFalsa):

    def test_descarga_el_texto(self):
        self.usar_red(b'{"openapi": "3.0.0"}')
        self.assertIn("openapi", integraciones.descargar_especificacion("https://api.ejemplo.com/openapi.json"))

    def test_demasiado_grande(self):
        self.usar_red(b"x" * (integraciones.MAX_KB_ESPECIFICACION * 1024 + 1))
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "pesa más"):
            integraciones.descargar_especificacion("https://api.ejemplo.com/openapi.json")

    def test_no_descarga_de_la_red_interna(self):
        red = self.usar_red(resolver=ip_privada)
        with self.assertRaisesRegex(integraciones.ErrorIntegracion, "no es pública"):
            integraciones.descargar_especificacion("https://intranet/openapi.json")
        self.assertFalse(red.peticiones)


if __name__ == "__main__":
    unittest.main()
