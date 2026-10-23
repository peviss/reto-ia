"""Pruebas de app.py: validación de la entrada y manejo de errores de la IA.

Ninguna prueba llama de verdad a la IA: los modelos se sustituyen por otros falsos (FunctionModel).
Ejecutar:  python -m unittest discover -s tests -v
"""

import logging
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai.exceptions import ModelConnectionError, ModelHTTPError, ModelRateLimitError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import FunctionModel
from streamlit.runtime.secrets import Secrets
from streamlit.testing.v1 import AppTest

# Importar app.py fuera de «streamlit run» avisa de que no hay sesión: lo silenciamos
logging.getLogger("streamlit").setLevel(logging.ERROR)
import app  # noqa: E402

RUTA_APP = str(Path(__file__).parent.parent / "app.py")


def archivo(nombre, megas=0.01):
    return {"nombre": nombre, "datos": b"x" * int(megas * 1024 * 1024), "mime": "image/jpeg"}


def error_api(codigo, texto="error"):
    if codigo == 429:
        return ModelRateLimitError("falso", texto)
    return ModelHTTPError(codigo, "falso", {"message": texto})


class ModeloFalso(FunctionModel):
    """Imita un modelo de IA: lanza los errores que se le pasen, uno por llamada.

    Si se le acaban los errores, responde con un comprobante leído.
    """

    def __init__(self, *fallos):
        self.fallos = list(fallos)
        self.llamadas = 0
        super().__init__(self.responder)

    def responder(self, _mensajes, info):
        self.llamadas += 1
        if self.fallos:
            raise self.fallos.pop(0)
        comprobante = {"archivo": "t.jpg", "comercio": "Bar Inventado", "fecha": "2025-10-01",
                       "total": 12.5, "categoria": "Otros", "legible": True}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"response": [comprobante]})])


class Validacion(unittest.TestCase):

    def test_CA8_sin_archivos(self):
        self.assertIn("Falta el extracto", app.validar(None, []))
        self.assertIn("Faltan los tickets", app.validar(archivo("e.csv"), []))

    def test_CA9_demasiados_comprobantes(self):
        aviso = app.validar(archivo("e.csv"), [archivo(f"t{i}.jpg") for i in range(21)])
        self.assertIn("máximo es 20", aviso)

    def test_CA9_archivo_de_mas_de_8_MB(self):
        aviso = app.validar(archivo("e.csv"), [archivo("grande.jpg", megas=8.1)])
        self.assertIn("grande.jpg", aviso)

    def test_entrada_correcta(self):
        self.assertIsNone(app.validar(archivo("e.csv"), [archivo(f"t{i}.jpg") for i in range(20)]))


class ErroresDeLaIA(unittest.TestCase):

    def llamar(self, modelo):
        with mock.patch.object(app.time, "sleep"), mock.patch.object(app.st, "info"):
            return app.llamar_ia(modelo, ["hola"], "prompt", app.Comprobante)

    def test_CA12_cuota_agotada_reintenta_una_vez(self):
        modelo = ModeloFalso(error_api(429), error_api(429))
        datos, error = self.llamar(modelo)
        self.assertIsNone(datos)
        self.assertEqual(modelo.llamadas, 2)
        self.assertIn("cuota gratuita", error)

    def test_clave_no_valida(self):
        _, error = self.llamar(ModeloFalso(error_api(400, "API key not valid")))
        self.assertIn("clave no válida", error)

    def test_archivo_danado(self):
        _, error = self.llamar(ModeloFalso(error_api(400)))
        self.assertIn("no ha podido abrir", error)

    def test_servidor_caido(self):
        _, error = self.llamar(ModeloFalso(error_api(503)))
        self.assertIn("no responde", error)

    def test_sin_red(self):
        _, error = self.llamar(ModeloFalso(ModelConnectionError("falso", "sin red")))
        self.assertIn("No hay conexión", error)


class ModeloDeReserva(unittest.TestCase):
    """Si Gemini falla, la misma llamada se repite con Claude (FallbackModel)."""

    def llamar(self, modelo):
        with mock.patch.object(app.time, "sleep") as espera, mock.patch.object(app.st, "info"):
            resultado = app.llamar_ia(modelo, ["hola"], "prompt", app.Comprobante)
        return resultado, espera

    def test_CA18_gemini_sin_cuota_usa_claude_sin_esperar(self):
        gemini, claude = ModeloFalso(error_api(429)), ModeloFalso()
        (datos, error), espera = self.llamar(FallbackModel(gemini, claude))
        self.assertIsNone(error)
        self.assertEqual(datos[0]["comercio"], "Bar Inventado")
        self.assertEqual((gemini.llamadas, claude.llamadas), (1, 1))
        espera.assert_not_called()

    def test_fallan_los_dos_cuenta_el_ultimo(self):
        gemini, claude = ModeloFalso(error_api(429)), ModeloFalso(error_api(503))
        (datos, error), _ = self.llamar(FallbackModel(gemini, claude))
        self.assertIsNone(datos)
        self.assertIn("no responde", error)

    def test_obtener_modelo_segun_claves(self):
        def secretos(claves):
            return mock.patch.object(app.st, "secrets", claves)
        with secretos({}):
            self.assertIsNone(app.obtener_modelo())
        with secretos({"GEMINI_API_KEY": "falsa"}):
            self.assertEqual(app.obtener_modelo().model_name, app.MODELO_GEMINI)
        with secretos({"ANTHROPIC_API_KEY": "falsa"}):
            self.assertEqual(app.obtener_modelo().model_name, app.MODELO_RESERVA)
        with secretos({"GEMINI_API_KEY": "falsa", "ANTHROPIC_API_KEY": "falsa"}):
            self.assertIsInstance(app.obtener_modelo(), FallbackModel)


class Interfaz(unittest.TestCase):
    """Ejecuta app.py con AppTest, sin navegador y con secretos vacíos."""

    def setUp(self):
        # Si algo intentara crear un cliente real, la prueba falla en lugar de gastar cuota
        parches = [
            mock.patch.object(app.Agent, "run_sync", side_effect=AssertionError("llamada real a la IA")),
            # AppTest también lee .streamlit/secrets.toml: hacemos como si no hubiera ninguna clave
            mock.patch.object(Secrets, "__getitem__", side_effect=KeyError("GEMINI_API_KEY")),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.at = AppTest.from_file(RUTA_APP, default_timeout=30)
        self.at.run()

    def boton(self, texto):
        return next(b for b in self.at.button if texto in b.label)

    def test_arranca_sin_errores(self):
        self.assertFalse(self.at.exception)
        self.assertEqual(self.at.title[0].value, "🧾 Cuadra tus gastos")

    def test_CA8_cuadrar_sin_archivos(self):
        self.boton("Cuadrar gastos").click().run()
        self.assertIn("Falta el extracto", self.at.warning[0].value)
        self.assertFalse(self.at.error)

    def test_CA11_sin_clave(self):
        self.boton("Probar con datos de ejemplo").click().run()
        self.boton("Cuadrar gastos").click().run()
        self.assertFalse(self.at.exception)
        self.assertIn("falta la clave", self.at.error[0].value)


if __name__ == "__main__":
    unittest.main()
