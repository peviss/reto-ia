"""Pruebas de app.py: validación de la entrada y manejo de errores de la IA.

Ninguna prueba llama de verdad a la IA: los modelos se sustituyen por otros falsos (FunctionModel).
Ejecutar:  python -m unittest discover -s tests -v
"""

import base64
import json
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

    def __init__(self, *fallos, nombre=None):
        self.fallos = list(fallos)
        self.llamadas = 0
        super().__init__(self.responder, model_name=nombre)  # nombre: para imitar a Gemini o a Claude

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
        # Los tickets son opcionales: con el extracto basta
        self.assertIsNone(app.validar(archivo("e.csv"), []))

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
    """F4: preguntar sobre lo extraído. Los totales los calcula Python, no la IA."""

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
        self.assertIn("modelo", turno)  # se enseña debajo de la respuesta

    def test_CA24_recuerda_las_preguntas_anteriores(self):
        modelo = ModeloQueConsulta({"justificante": "sin"})
        primero, _ = self.preguntar(modelo, "¿Cuánto en restauración?")
        segundo, _ = self.preguntar(modelo, "¿Y cuáles no tienen ticket?", [primero])
        self.assertEqual(modelo.vistos[-1], ["¿Cuánto en restauración?", "¿Y cuáles no tienen ticket?"])
        self.assertEqual(segundo["consultas"][0]["numero_de_gastos"], 3)

    def test_CA26_el_turno_se_puede_guardar_sin_los_datos_del_cuadre(self):
        turno, _ = self.preguntar(ModeloQueConsulta({"categoria": "Restauración"}), "¿Cuánto en restauración?")
        texto = json.dumps(turno)  # IndexedDB guarda lo que se puede pasar a JSON
        self.assertNotIn("CAFETERIA LA PLAZA,", texto)  # las instrucciones (con el CSV) no se guardan
        # Lo guardado vuelve a servir de historial en la siguiente pregunta
        modelo = ModeloQueConsulta({"justificante": "sin"})
        self.preguntar(modelo, "¿Y sin ticket?", [json.loads(texto)])
        self.assertEqual(modelo.vistos[-1], ["¿Cuánto en restauración?", "¿Y sin ticket?"])

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

    def test_elegir_un_modelo_en_avanzado(self):
        solo_gemini, solo_claude = list(app.OPCIONES_MODELO)[1:]
        with mock.patch.object(app.st, "secrets", {"GEMINI_API_KEY": "falsa", "ANTHROPIC_API_KEY": "falsa"}):
            self.assertEqual(app.opciones_modelo(), list(app.OPCIONES_MODELO))
            self.assertEqual(app.obtener_modelo(solo_gemini).model_name, app.MODELO_GEMINI)
            self.assertEqual(app.obtener_modelo(solo_claude).model_name, app.MODELO_RESERVA)
            self.assertIsInstance(app.obtener_modelo(app.AUTOMATICO), FallbackModel)
        with mock.patch.object(app.st, "secrets", {"GEMINI_API_KEY": "falsa"}):
            # Sin clave de Anthropic no se ofrece Claude, y si se pide igualmente no hay modelo
            self.assertEqual(app.opciones_modelo(), [app.AUTOMATICO, solo_gemini])
            self.assertIsNone(app.obtener_modelo(solo_claude))


class QueModeloSeUsa(unittest.TestCase):
    """La pantalla dice con qué modelo se lee y cuál ha respondido de verdad."""

    def llamar(self, modelo):
        sesion = {}
        with mock.patch.object(app.st, "session_state", sesion), mock.patch.object(app.st, "info"):
            app.llamar_ia(modelo, ["hola"], "prompt", app.Comprobante)
        return sesion["llamadas_ia"]

    def test_nombres_para_el_usuario(self):
        self.assertEqual(app.nombre_modelo("gemini-3.8-flash"), "Gemini (gemini-3.8-flash)")
        self.assertEqual(app.nombre_modelo("claude-haiku-5-5"), "Claude (claude-haiku-5-5)")

    def test_apunta_el_modelo_que_responde(self):
        llamadas = self.llamar(ModeloFalso(nombre="gemini-falso"))
        self.assertEqual([(l["principal"], l["modelo"]) for l in llamadas],
                         [("Gemini (gemini-falso)", "Gemini (gemini-falso)")])
        self.assertIn("Leído con Gemini (gemini-falso): 1 llamada", app.resumen_llamadas(llamadas))

    def test_avisa_si_responde_el_de_reserva(self):
        gemini, claude = ModeloFalso(error_api(429), nombre="gemini-falso"), ModeloFalso(nombre="claude-falso")
        llamadas = self.llamar(FallbackModel(gemini, claude))
        resumen = app.resumen_llamadas(llamadas)
        self.assertIn("Leído con Claude (claude-falso)", resumen)
        self.assertIn("Gemini (gemini-falso) no respondía", resumen)

    def test_sin_llamadas_lo_dice(self):
        self.assertIn("No se ha llamado a la IA", app.resumen_llamadas([]))


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

    def test_CA30_integraciones_sin_la_clave(self):
        almacen.guardar_integracion({"id": "i1", "nombre": "Contabilidad", "clave": "secreta"})
        self.assertEqual(almacen.integracion("i1"), {"id": "i1", "nombre": "Contabilidad"})
        self.assertNotIn("clave", str(self.estado["orden_nueva"]["integraciones"]))
        # Guardar y eliminar en la misma ejecución: una sola orden que la quita
        almacen.eliminar_integracion("i1")
        self.assertEqual(almacen.integraciones(), [])
        self.assertEqual(self.estado["orden_nueva"]["integraciones"], {})
        self.assertEqual(self.estado["orden_nueva"]["quitar_integraciones"], ["i1"])

    def test_borrar_todo(self):
        almacen.guardar_lecturas({"x": [1]})
        almacen.borrar_todo()
        self.assertEqual(self.estado["guardado"],
                         {"lecturas": {}, "cuadres": {}, "conversaciones": {}, "integraciones": {}})
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

    def test_CA26_conversaciones_por_cuadre(self):
        turno = {"pregunta": "p", "respuesta": "r", "consultas": [], "mensajes": []}
        almacen.guardar_cuadre({"id": "a", "nombre": "A"})
        almacen.guardar_conversacion("a", [turno])
        self.assertEqual(almacen.conversacion("a"), [turno])
        self.assertEqual(almacen.conversacion("otro"), [])
        self.assertEqual(self.estado["orden_nueva"]["conversaciones"], {"a": [turno]})
        # Preguntar no cambia el cuadre (ni su fecha en el historial)
        self.assertNotIn("conversacion", almacen.cuadre("a"))
        # Al eliminar el cuadre se va su conversación y no se vuelve a mandar
        almacen.eliminar_cuadre("a")
        self.assertEqual(almacen.conversacion("a"), [])
        self.assertEqual(self.estado["orden_nueva"]["conversaciones"], {})
        self.assertEqual(self.estado["orden_nueva"]["quitar"], ["a"])

    def test_CA26_borrar_la_conversacion(self):
        almacen.guardar_conversacion("a", [{"pregunta": "p"}])
        almacen.guardar_conversacion("a", [])
        self.assertEqual(almacen.conversacion("a"), [])
        self.assertEqual(self.estado["orden_nueva"]["conversaciones"], {"a": []})  # el navegador la borra

    def test_CA26_al_cargar_llegan_las_conversaciones(self):
        self.estado["almacen"] = mock.Mock(guardado={"lecturas": {}, "cuadres": {},
                                                     "conversaciones": {"a": [{"pregunta": "p"}]}})
        almacen._al_cargar()
        self.assertEqual(almacen.conversacion("a"), [{"pregunta": "p"}])

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
        # Un cuadre nuevo empieza sin conversación
        self.at.session_state["conversacion"] = [{"pregunta": "p", "respuesta": "r", "consultas": [], "mensajes": []}]
        self.boton("Nuevo cuadre").click().run()
        self.assertEqual(self.at.session_state["conversacion"], [])

    def test_CA26_al_abrir_un_cuadre_sale_su_conversacion(self):
        cuadre = {"id": "c1", "nombre": "Octubre", "extracto": "extracto_octubre.csv", "fecha": "31/10/26, 10:00",
                  "actualizado": 1, "movimientos": datos_ejemplo.MOVIMIENTOS, "leidos": datos_ejemplo.COMPROBANTES}
        turno = {"pregunta": "¿Cuánto en restauración?", "respuesta": "25,60 €", "consultas": [], "mensajes": []}
        self.at.session_state["guardado"] = {"lecturas": {}, "cuadres": {"c1": cuadre}, "conversaciones": {"c1": [turno]}}
        self.at.session_state["guardado_cargado"] = True
        self.at.run()
        self.boton("Octubre").click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual([m.markdown[0].value for m in self.at.chat_message], ["¿Cuánto en restauración?", "25,60 €"])

    def abrir_octubre(self, integraciones_guardadas=None):
        cuadre = {"id": "c1", "nombre": "Octubre", "extracto": "extracto_octubre.csv", "fecha": "31/10/26, 10:00",
                  "actualizado": 1, "movimientos": datos_ejemplo.MOVIMIENTOS, "leidos": datos_ejemplo.COMPROBANTES}
        self.at.session_state["guardado"] = {"lecturas": {}, "cuadres": {"c1": cuadre},
                                             "integraciones": integraciones_guardadas or {}}
        self.at.session_state["guardado_cargado"] = True
        self.at.run()
        self.boton("Octubre").click().run()

    def test_CA30_sin_integraciones_se_puede_configurar_una(self):
        self.abrir_octubre()
        # Sin secretos de Google Drive solo sale la integración propia
        self.assertEqual(self.at.radio(key="destino").options, ["Integración propia"])
        self.at.button(key="nueva_integracion").click().run()
        self.assertFalse(self.at.exception)
        self.assertTrue(self.at.session_state["form_integracion"]["id"] == "")  # el diálogo, con una nueva

    def test_CA30_enviar_con_una_integracion_guardada(self):
        config = {**app.integraciones.configuracion_nueva(), "id": "i1", "nombre": "Contabilidad",
                  "url": "https://api.ejemplo.com/gastos", "autenticacion": "cabecera", "cabecera_clave": "X-API-Key",
                  "envio": "uno_por_gasto", "campos": [{"destino": "amount", "origen": "importe",
                                                        "formato": "centimos", "valor": ""}]}
        self.abrir_octubre({"i1": config})
        self.assertEqual(self.at.selectbox(key="integracion_elegida").value, "i1")
        with mock.patch.object(app.integraciones, "enviar", return_value=12) as enviar:
            self.at.text_input(key="clave_i1").set_value("secreta")
            self.at.button(key="enviar").click().run()
            self.assertFalse(self.at.exception)
            enviada, clave, filas, datos = enviar.call_args.args
            self.assertEqual((enviada["nombre"], clave, len(filas), datos["cuadre"]), ("Contabilidad", "secreta", 12, "Octubre"))
            self.assertIn("12 gastos", self.at.success[0].value)
            # Si falla, el mensaje claro de integraciones.py, sin trazas
            enviar.side_effect = app.integraciones.ErrorIntegracion("Contabilidad ha rechazado los datos (error 422).")
            self.at.button(key="enviar").click().run()
            self.assertIn("error 422", self.at.error[0].value)

    def test_CA29_google_drive_con_la_cuenta_del_usuario(self):
        cuadre = {"id": "c1", "nombre": "Octubre", "extracto": "extracto_octubre.csv", "fecha": "31/10/26, 10:00",
                  "actualizado": 1, "movimientos": datos_ejemplo.MOVIMIENTOS, "leidos": datos_ejemplo.COMPROBANTES}
        self.at.session_state["guardado"] = {"lecturas": {}, "cuadres": {"c1": cuadre}}
        self.at.session_state["guardado_cargado"] = True
        with mock.patch.object(app.drive, "client_id", return_value="id.apps.googleusercontent.com"):
            self.at.run()
            self.boton("Octubre").click().run()
            self.assertEqual(self.at.radio(key="destino").options, ["Google Drive", "Integración propia"])
            # Con Google Drive no hay botón del servidor: lo sube el navegador del usuario (drive.py)
            self.at.radio(key="destino").set_value("Google Drive").run()
            self.assertFalse(self.at.exception)
            self.assertFalse([b for b in self.at.button if b.key == "enviar"])


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


class ModeloQueProponeIntegracion(FunctionModel):
    """Imita al asistente: devuelve una configuración y guarda lo que ha recibido."""

    PROPUESTA = {"nombre": "Contabilidad", "url": "https://api.ejemplo.com/v1/gastos", "metodo": "POST",
                 "autenticacion": "bearer", "envio": "uno_por_gasto",
                 "campos": [{"destino": "date", "origen": "fecha", "formato": "fecha_dma"},
                            {"destino": "amount", "origen": "importe", "formato": "negativo"},
                            {"destino": "account", "origen": "fijo", "valor": "629"}],
                 "notas": "He elegido POST /v1/gastos. Revise la cuenta contable."}

    def __init__(self):
        self.recibido = []
        super().__init__(self.responder)

    def responder(self, mensajes, info):
        self.recibido = [p.content for m in mensajes for p in m.parts if p.part_kind == "user-prompt"]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"response": [self.PROPUESTA]})])


class AsistenteDeIntegraciones(unittest.TestCase):
    """CA31: la IA lee la especificación de una API y propone la configuración (no envía nada)."""

    def setUp(self):
        parche = mock.patch.object(app.st, "session_state", {})
        parche.start()
        self.addCleanup(parche.stop)

    def test_CA31_propone_los_campos(self):
        modelo = ModeloQueProponeIntegracion()
        config, error = app.leer_especificacion(modelo, "openapi: 3.0.0\npaths: {/v1/gastos: {post: {}}}",
                                                "un gasto por movimiento")
        self.assertIsNone(error)
        self.assertEqual(config["url"], "https://api.ejemplo.com/v1/gastos")
        self.assertEqual(config["campos"][2], {"destino": "account", "origen": "fijo", "formato": "tal_cual", "valor": "629"})
        self.assertEqual(config["cabecera_clave"], "")  # lo que no dice la IA, con su valor por defecto
        self.assertIsNone(app.integraciones.validar_configuracion(config))
        texto = " ".join(map(str, modelo.recibido[0]))
        self.assertIn("un gasto por movimiento", texto)
        self.assertIn("/v1/gastos", texto)

    def test_CA31_la_propuesta_se_puede_enviar(self):
        config, _ = app.leer_especificacion(ModeloQueProponeIntegracion(), "openapi: 3.0.0")
        gastos, _, _ = app.cuadrar(datos_ejemplo.MOVIMIENTOS, datos_ejemplo.COMPROBANTES)
        filas = app.integraciones.filas_para_enviar(gastos, datos_ejemplo.COMPROBANTES, "Octubre")
        primero = app.integraciones.cuerpos(config, filas, {})[0]
        self.assertEqual(primero, {"date": "01/10/2026", "amount": -230.0, "account": "629"})

    def test_especificacion_enorme_se_recorta(self):
        modelo = ModeloQueProponeIntegracion()
        app.leer_especificacion(modelo, "x" * (app.MAX_CARACTERES_ESPECIFICACION + 1000))
        self.assertIn("[… recortada]", modelo.recibido[0][-1])
        self.assertLess(len(modelo.recibido[0][-1]), app.MAX_CARACTERES_ESPECIFICACION + 100)

    def test_si_falla_la_ia_mensaje_claro(self):
        config, error = app.leer_especificacion(ModeloFalso(error_api(401), error_api(401)), "openapi: 3.0.0")
        self.assertIsNone(config)
        self.assertIn("clave no válida", error)


if __name__ == "__main__":
    unittest.main()
