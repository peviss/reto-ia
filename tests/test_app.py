"""Pruebas de app.py: validación de la entrada y manejo de errores de la IA.

Ninguna prueba llama de verdad a la IA: los modelos se sustituyen por otros falsos (FunctionModel).
Ejecutar:  python -m unittest discover -s tests -v
"""

import base64
import logging
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai.exceptions import ModelConnectionError, ModelHTTPError, ModelRateLimitError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import FunctionModel
from streamlit.runtime.secrets import Secrets
from streamlit.testing.v1 import AppTest

# Importar app.py fuera de «streamlit run» avisa de que no hay sesión: lo silenciamos
logging.getLogger("streamlit").setLevel(logging.ERROR)
import almacen  # noqa: E402
import app  # noqa: E402
import datos_ejemplo  # noqa: E402

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


class ModeloQueConsulta(FunctionModel):
    """Imita la conversación: primero pide sumar_gastos con unos filtros y luego responde con el total."""

    def __init__(self, filtros):
        self.filtros = filtros
        self.vistos = []  # textos de usuario que ha recibido en cada pregunta
        super().__init__(self.responder)

    def responder(self, mensajes, _info):
        devuelto = [p for p in mensajes[-1].parts if isinstance(p, ToolReturnPart)]
        if devuelto:
            return ModelResponse(parts=[TextPart(f"Total: {devuelto[0].content['total_euros']} €")])
        self.vistos.append([p.content for m in mensajes for p in m.parts if p.part_kind == "user-prompt"])
        return ModelResponse(parts=[ToolCallPart("sumar_gastos", self.filtros)])


class Conversacion(unittest.TestCase):
    """F5: preguntar sobre lo extraído. Los totales los calcula Python, no la IA."""

    def setUp(self):
        self.gastos, _, self.sueltos = app.cuadrar(datos_ejemplo.MOVIMIENTOS, datos_ejemplo.COMPROBANTES)
        self.datos = app.datos_para_conversar(datos_ejemplo.MOVIMIENTOS, datos_ejemplo.COMPROBANTES,
                                              self.gastos, self.sueltos)

    def preguntar(self, modelo, pregunta, turnos=()):
        with mock.patch.object(app.time, "sleep"), mock.patch.object(app.st, "info"):
            return app.conversar(modelo, pregunta, list(turnos), self.gastos, self.datos)

    def test_datos_incluyen_todo_lo_extraido(self):
        for texto in ["CAFETERIA LA PLAZA", "ticket_restaurante_efectivo.jpg", "Reembolso agrupado", "1200"]:
            self.assertIn(texto, self.datos)

    def test_CA23_el_total_lo_calcula_python(self):
        turno, error = self.preguntar(ModeloQueConsulta({"categoria": "Restauración"}), "¿Cuánto en restauración?")
        self.assertIsNone(error)
        self.assertEqual(turno["respuesta"], "Total: 25.6 €")
        self.assertEqual(turno["consultas"][0]["numero_de_gastos"], 2)

    def test_CA24_recuerda_las_preguntas_anteriores(self):
        modelo = ModeloQueConsulta({"justificante": "sin"})
        primero, _ = self.preguntar(modelo, "¿Cuánto en restauración?")
        segundo, _ = self.preguntar(modelo, "¿Y cuáles no tienen ticket?", [primero])
        self.assertEqual(modelo.vistos[-1], ["¿Cuánto en restauración?", "¿Y cuáles no tienen ticket?"])
        self.assertEqual(segundo["consultas"][0]["numero_de_gastos"], 3)

    def test_cuota_agotada_reintenta_una_vez(self):
        modelo = ModeloFalso(error_api(429), error_api(429))
        turno, error = self.preguntar(modelo, "hola")
        self.assertIsNone(turno)
        self.assertEqual(modelo.llamadas, 2)
        self.assertIn("cuota gratuita", error)


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


class LoGuardadoEnElNavegador(unittest.TestCase):
    """Lo ya leído (guardado en IndexedDB) no se vuelve a mandar a la IA. Sin navegador:
    lo que llegaría de IndexedDB se pone a mano en una session_state falsa (un dict)."""

    def setUp(self):
        self.estado = {"guardado": {"lecturas": {}, "cuadres": {}}}
        parche = mock.patch.object(app.st, "session_state", self.estado)
        parche.start()
        self.addCleanup(parche.stop)

    def test_huella_por_contenido(self):
        a, b = archivo("a.jpg"), {**archivo("otro_nombre.jpg")}
        self.assertEqual(almacen.huella("comprobante", a), almacen.huella("comprobante", b))
        self.assertNotEqual(almacen.huella("comprobante", a), almacen.huella("extracto", a))
        self.assertNotEqual(almacen.huella("comprobante", a), almacen.huella("comprobante", archivo("a.jpg", megas=0.02)))

    def test_CA19_extracto_ya_leido_no_llama_a_la_ia(self):
        extracto = archivo("e.csv")
        movimientos = [{"fecha": "2025-10-01", "concepto": "X", "importe": -5.0, "categoria": "Otros"}]
        self.estado["guardado"]["lecturas"][almacen.huella("extracto", extracto)] = movimientos
        modelo = ModeloFalso()
        self.assertEqual(app.leer_extracto_con_memoria(modelo, extracto), (movimientos, None))
        self.assertEqual(modelo.llamadas, 0)

    def test_CA19_solo_se_leen_los_comprobantes_nuevos(self):
        viejo, nuevo = archivo("renombrado.jpg"), {**archivo("t.jpg", megas=0.02)}
        guardado = {"archivo": "viejo.jpg", "comercio": "Tienda Guardada", "fecha": "2025-10-02",
                    "total": 3.0, "categoria": "Otros", "legible": True}
        self.estado["guardado"]["lecturas"][almacen.huella("comprobante", viejo)] = guardado
        modelo = ModeloFalso()  # responde con el comprobante «t.jpg»
        leidos, error = app.leer_comprobantes_con_memoria(modelo, [viejo, nuevo], mock.Mock())
        self.assertIsNone(error)
        self.assertEqual(modelo.llamadas, 1)
        self.assertEqual([c["archivo"] for c in leidos], ["renombrado.jpg", "t.jpg"])  # con el nombre de ahora
        # El nuevo queda pendiente de guardar en el navegador y ya se usa en esta sesión
        clave = almacen.huella("comprobante", nuevo)
        self.assertIn(clave, self.estado["orden_nueva"]["lecturas"])
        self.assertIn(clave, self.estado["guardado"]["lecturas"])

    def test_ilegibles_no_se_guardan(self):
        ilegible = {"archivo": "t.jpg", "comercio": "", "fecha": "", "total": 0.0, "categoria": "Otros", "legible": False}
        with mock.patch.object(app, "leer_comprobantes", return_value=([ilegible], None)):
            app.leer_comprobantes_con_memoria(None, [archivo("t.jpg")], mock.Mock())
        self.assertNotIn("orden_nueva", self.estado)

    def test_borrar_todo(self):
        almacen.guardar_lecturas({"x": [1]})
        almacen.borrar_todo()
        self.assertEqual(self.estado["guardado"], {"lecturas": {}, "cuadres": {}})
        self.assertEqual(self.estado["orden_nueva"], {**almacen._orden_vacia(), "borrar": True})

    def test_CA22_archivos_en_base64_y_sin_huerfanos(self):
        foto = archivo("t.jpg")
        clave = almacen.huella("comprobante", foto)
        almacen.guardar_archivos({clave: foto})
        self.assertEqual(base64.b64decode(self.estado["orden_nueva"]["archivos"][clave]["b64"]), foto["datos"])
        # Dos cuadres comparten el ticket: al eliminar uno, el archivo se queda; al eliminar el otro, se borra
        almacen.guardar_cuadre({"id": "a", "nombre": "A", "huellas": {"t.jpg": clave}})
        almacen.guardar_cuadre({"id": "b", "nombre": "B", "huellas": {"otro_nombre.jpg": clave}})
        almacen.eliminar_cuadre("a")
        self.assertEqual(self.estado["orden_nueva"]["quitar_archivos"], [])
        almacen.eliminar_cuadre("b")
        self.assertEqual(self.estado["orden_nueva"]["quitar_archivos"], [clave])
        self.assertNotIn(clave, self.estado["orden_nueva"]["archivos"])  # ya no se manda

    def test_ticket_sustituido_se_borra(self):
        almacen.guardar_cuadre({"id": "a", "nombre": "A", "huellas": {"t.jpg": "vieja"}})
        almacen.guardar_cuadre({"id": "a", "nombre": "A", "huellas": {"t.jpg": "nueva"}})
        self.assertEqual(self.estado["orden_nueva"]["quitar_archivos"], ["vieja"])

    def test_orden_sin_confirmar_se_junta_con_la_nueva(self):
        with mock.patch.object(almacen, "_componente") as componente:
            almacen.guardar_lecturas({"x": [1]})
            almacen.sincronizar()
            primera = self.estado["orden_enviada"]
            almacen.guardar_lecturas({"y": [2]})  # el navegador aún no ha confirmado la primera
            almacen.sincronizar()
            self.assertEqual(set(self.estado["orden_enviada"]["lecturas"]), {"x", "y"})
            # El navegador confirma: deja de mandarse
            self.estado["almacen"] = mock.Mock(hecha=self.estado["orden_enviada"]["id"])
            almacen._al_hacerse()
            self.assertNotIn("orden_enviada", self.estado)
            self.assertNotEqual(primera["id"], componente.call_args.kwargs["data"]["orden"]["id"])

    def test_CA20_historial_del_mas_reciente_al_mas_antiguo(self):
        with mock.patch.object(almacen.time, "time", side_effect=[1, 2, 3]):
            for nombre in ["septiembre", "octubre", "noviembre"]:
                almacen.guardar_cuadre({"id": nombre, "nombre": nombre})
        self.assertEqual([c["nombre"] for c in almacen.cuadres()], ["noviembre", "octubre", "septiembre"])
        almacen.eliminar_cuadre("octubre")
        self.assertEqual([c["nombre"] for c in almacen.cuadres()], ["noviembre", "septiembre"])
        self.assertEqual(self.estado["orden_nueva"]["quitar"], ["octubre"])
        self.assertNotIn("octubre", self.estado["orden_nueva"]["cuadres"])

    def test_cuadre_de_la_version_anterior_aparece_en_el_historial(self):
        # Antes se guardaba un solo cuadre con la clave «ultimo», sin id ni nombre
        anterior = {"extracto": "e.csv", "movimientos": [], "leidos": [], "fecha": "1/10/26, 9:00"}
        self.estado["almacen"] = mock.Mock(guardado={"lecturas": {}, "cuadres": {"ultimo": anterior}})
        almacen._al_cargar()
        self.assertEqual(almacen.cuadre("ultimo")["nombre"], "e.csv")
        self.assertTrue(almacen.cargado())


class EditarUnCuadre(unittest.TestCase):

    def test_CA21_se_suman_los_comprobantes_nuevos(self):
        anteriores = [{"archivo": "a.jpg", "total": 1.0}, {"archivo": "b.jpg", "total": 2.0}]
        nuevos = [{"archivo": "b.jpg", "total": 5.0}, {"archivo": "c.jpg", "total": 3.0}]
        juntos = app.juntar_comprobantes(anteriores, nuevos)
        self.assertEqual([(c["archivo"], c["total"]) for c in juntos], [("a.jpg", 1.0), ("b.jpg", 5.0), ("c.jpg", 3.0)])

    def test_CA21_validar_al_editar(self):
        self.assertIn("Suba más tickets", app.validar(None, [], editando=True))
        self.assertIsNone(app.validar(None, [archivo("t.jpg")], editando=True))  # el extracto ya lo tiene
        self.assertIsNone(app.validar(archivo("e.csv"), [], editando=True))  # cambiar solo el extracto
        self.assertIn("máximo es 20", app.validar(None, [archivo(f"t{i}.jpg") for i in range(21)], editando=True))


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

    def test_CA20_abrir_un_cuadre_del_historial(self):
        # Lo que mandaría el navegador desde IndexedDB: el cuadre del ejemplo bien leído
        cuadre = {"id": "c1", "nombre": "Octubre", "extracto": "extracto_octubre.csv", "fecha": "31/10/26, 10:00",
                  "actualizado": 1, "movimientos": datos_ejemplo.MOVIMIENTOS, "leidos": datos_ejemplo.COMPROBANTES}
        self.at.session_state["guardado"] = {"lecturas": {}, "cuadres": {"c1": cuadre}}
        self.at.session_state["guardado_cargado"] = True
        self.at.run()
        self.boton("Octubre").click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual(self.at.subheader[0].value, "📂 Octubre")
        self.assertEqual(self.at.metric[0].value, "10")  # CA1: 10 gastos
        self.assertEqual(self.at.metric[1].value, "7")
        # Editar sin subir nada nuevo: aviso, sin llamar a la IA
        self.boton("Añadir al cuadre").click().run()
        self.assertIn("Suba más tickets", self.at.warning[0].value)
        # Nuevo cuadre: vuelve a la página vacía
        self.boton("Nuevo cuadre").click().run()
        self.assertEqual(self.at.subheader[0].value, "Nuevo cuadre")
        self.assertFalse(self.at.metric)

    def test_CA24_conversacion_sin_clave_y_al_cambiar_de_cuadre(self):
        cuadre = {"id": "c1", "nombre": "Octubre", "extracto": "extracto_octubre.csv", "fecha": "31/10/26, 10:00",
                  "actualizado": 1, "movimientos": datos_ejemplo.MOVIMIENTOS, "leidos": datos_ejemplo.COMPROBANTES}
        self.at.session_state["guardado"] = {"lecturas": {}, "cuadres": {"c1": cuadre}}
        self.at.session_state["guardado_cargado"] = True
        self.at.run()
        self.boton("Octubre").click().run()
        self.at.chat_input[0].set_value("¿Cuánto he gastado?").run()
        self.assertFalse(self.at.exception)
        self.assertIn("falta la clave", self.at.error[0].value)
        # Al cambiar de cuadre, la conversación empieza de cero
        self.at.session_state["conversacion"] = [{"pregunta": "p", "respuesta": "r", "consultas": [], "mensajes": []}]
        self.boton("Nuevo cuadre").click().run()
        self.assertEqual(self.at.session_state["conversacion"], [])

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
