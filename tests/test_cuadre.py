"""Pruebas de las reglas de cuadre.py con los datos de ejemplo (sin IA).

Cada prueba lleva en el nombre el criterio de aceptación (CA) de ESPECIFICACION §5 que comprueba.
Ejecutar:  python -m unittest discover -s tests -v
"""

import copy
import unittest

from cuadre import consultar_gastos, cuadrar
from datos_ejemplo import COMPROBANTES, MOVIMIENTOS, comprobante


def cuadrar_ejemplo(**ajustes):
    # Copias para que ninguna prueba modifique los datos de las demás
    return cuadrar(copy.deepcopy(MOVIMIENTOS), copy.deepcopy(COMPROBANTES), **ajustes)


def fila(gastos, concepto, fecha=None):
    """Filas de la tabla de gastos cuyo concepto contiene el texto (y con esa fecha, si se da)."""
    filas = gastos[gastos["Concepto"].str.contains(concepto)]
    if fecha:
        filas = filas[filas["Fecha"] == fecha]
    return filas


class CriteriosDeAceptacion(unittest.TestCase):

    def test_CA1_caso_principal(self):
        gastos, resumen, sueltos = cuadrar_ejemplo()
        con = gastos[gastos["Comprobante"] != ""]
        self.assertEqual(gastos["Mov."].nunique(), 10)
        self.assertEqual(con["Mov."].nunique(), 7)
        self.assertEqual(len(gastos[gastos["Estado"] == "✅ Con comprobante"]), 6)
        self.assertEqual(gastos[gastos["Estado"].str.startswith("🔗")]["Mov."].nunique(), 1)
        self.assertEqual(len(sueltos), 1)
        # El resumen por categoría suma lo mismo que la tabla de gastos
        self.assertAlmostEqual(resumen["Total (€)"].sum(), gastos["Importe (€)"].sum(), places=2)

    def test_CA2_fecha_del_banco_posterior(self):
        gastos, _, _ = cuadrar_ejemplo()
        self.assertEqual(fila(gastos, "GASOLINERA")["Comprobante"].tolist(), ["ticket_gasolinera.jpg"])

    def test_CA3_mismo_importe_dos_veces(self):
        gastos, _, _ = cuadrar_ejemplo()
        self.assertEqual(fila(gastos, "CAFETERIA", "2026-10-10")["Comprobante"].tolist(), ["ticket_cafeteria.jpg"])
        self.assertEqual(fila(gastos, "CAFETERIA", "2026-10-24")["Estado"].tolist(), ["⚠️ Falta comprobante"])

    def test_CA4_gastos_sin_comprobante(self):
        gastos, _, _ = cuadrar_ejemplo()
        faltan = gastos[gastos["Comprobante"] == ""]["Concepto"].tolist()
        self.assertTrue(any("AUTONOMOS" in c for c in faltan))
        self.assertTrue(any("MEGAMARKET" in c for c in faltan))

    def test_CA5_pago_en_efectivo(self):
        _, _, sueltos = cuadrar_ejemplo()
        self.assertEqual(sueltos["Archivo"].tolist(), ["ticket_restaurante_efectivo.jpg"])
        self.assertEqual(sueltos["Motivo"].tolist(), ["No aparece en el extracto"])

    def test_CA6_ingresos_excluidos(self):
        gastos, _, _ = cuadrar_ejemplo()
        self.assertTrue(fila(gastos, "TRANSF RECIBIDA").empty)

    def test_CA7_factura_pdf(self):
        gastos, _, _ = cuadrar_ejemplo()
        luz = fila(gastos, "ELECTRICA")
        self.assertEqual(luz["Comprobante"].tolist(), ["factura_luz.pdf"])
        self.assertEqual(luz["Categoría"].tolist(), ["Suministros (luz, agua, gas)"])

    def test_CA10_foto_ilegible(self):
        comprobantes = copy.deepcopy(COMPROBANTES) + [comprobante("paisaje.jpg", "", "", 0.0, "Otros", legible=False)]
        _, _, sueltos = cuadrar(copy.deepcopy(MOVIMIENTOS), comprobantes)
        self.assertEqual(sueltos.loc[sueltos["Archivo"] == "paisaje.jpg", "Motivo"].tolist(), ["No se ha podido leer"])

    def test_CA13_tolerancia_cero(self):
        gastos, _, _ = cuadrar_ejemplo(tolerancia_dias=0)
        # La gasolinera (ticket 05/10, banco 06/10) ya no cuadra; la cafetería (misma fecha) sí
        self.assertEqual(fila(gastos, "GASOLINERA")["Estado"].tolist(), ["⚠️ Falta comprobante"])
        self.assertEqual(fila(gastos, "CAFETERIA", "2026-10-10")["Comprobante"].tolist(), ["ticket_cafeteria.jpg"])

    def test_CA15_reembolso_agrupado(self):
        gastos, resumen, _ = cuadrar_ejemplo()
        marta = fila(gastos, "MARTA")
        self.assertEqual(len(marta), 3)
        self.assertEqual(marta["Mov."].nunique(), 1)
        self.assertAlmostEqual(marta["Importe (€)"].sum(), 51.65, places=2)
        self.assertEqual(sorted(marta["Comprobante"]),
                         ["reembolso_copisteria.jpg", "reembolso_ferreteria.jpg", "reembolso_fruteria.jpg"])
        # Cada compra suma en su categoría (la fruta en Alimentación, no en «Otros»)
        self.assertIn("Alimentación", marta["Categoría"].tolist())
        self.assertFalse(marta["Estado"].str.contains("revisar").any())

    def test_CA16_reembolso_ambiguo(self):
        movimientos = [{"fecha": "2026-10-30", "concepto": "TRANSF REEMBOLSO", "importe": -30.00, "categoria": "Otros"}]
        comprobantes = [comprobante(f"t{i}.jpg", f"Tienda {i}", "2026-10-20", total, "Otros")
                        for i, total in enumerate([10.00, 20.00, 15.00, 15.00])]
        gastos, _, _ = cuadrar(movimientos, comprobantes)
        self.assertAlmostEqual(gastos["Importe (€)"].sum(), 30.00, places=2)
        self.assertTrue(gastos["Estado"].str.contains("revisar").all())

    def test_CA17_sin_busqueda_de_reembolsos(self):
        gastos, _, sueltos = cuadrar_ejemplo(ventana_reembolso=0)
        self.assertEqual(fila(gastos, "MARTA")["Estado"].tolist(), ["⚠️ Falta comprobante"])
        for archivo in ["reembolso_copisteria.jpg", "reembolso_ferreteria.jpg", "reembolso_fruteria.jpg"]:
            self.assertIn(archivo, sueltos["Archivo"].tolist())


class Conversacion(unittest.TestCase):
    """consultar_gastos: lo que suma Python cuando se pregunta en la conversación (F5)."""

    def setUp(self):
        self.gastos, self.resumen, _ = cuadrar_ejemplo()

    def test_CA23_total_de_una_categoria_igual_que_la_tabla(self):
        resultado = consultar_gastos(self.gastos, categoria="Restauración")
        total_tabla = self.resumen.set_index("Categoría").loc["Restauración", "Total (€)"]
        self.assertAlmostEqual(resultado["total_euros"], total_tabla, places=2)
        self.assertEqual(resultado["numero_de_gastos"], 2)

    def test_CA23_gastos_sin_justificante(self):
        resultado = consultar_gastos(self.gastos, justificante="sin")
        self.assertAlmostEqual(resultado["total_euros"], 230.00 + 35.99 + 12.80, places=2)
        self.assertEqual(resultado["numero_de_gastos"], 3)

    def test_CA23_por_fechas_un_reembolso_cuenta_una_vez(self):
        resultado = consultar_gastos(self.gastos, desde="2026-10-20", hasta="2026-10-31")
        self.assertAlmostEqual(resultado["total_euros"], 18.50 + 12.80 + 51.65, places=2)
        self.assertEqual(resultado["numero_de_gastos"], 3)

    def test_por_texto_sin_tildes_ni_mayusculas(self):
        self.assertAlmostEqual(consultar_gastos(self.gastos, texto="Cafetería")["total_euros"], 25.60, places=2)
        self.assertEqual(consultar_gastos(self.gastos, texto="ferreteria")["numero_de_gastos"], 1)
        self.assertEqual(consultar_gastos(self.gastos, texto="no existe")["total_euros"], 0)


class CasosLimite(unittest.TestCase):

    def test_extracto_sin_gastos(self):
        gastos, resumen, _ = cuadrar([MOVIMIENTOS[1]], [])
        self.assertTrue(gastos.empty)
        self.assertTrue(resumen.empty)

    def test_categoria_inventada_pasa_a_otros(self):
        movimientos = [{"fecha": "2026-10-01", "concepto": "X", "importe": -5.0, "categoria": "Ocio"}]
        gastos, _, _ = cuadrar(movimientos, [])
        self.assertEqual(gastos["Categoría"].tolist(), ["Otros"])

    def test_ticket_sin_fecha_cuadra_por_importe(self):
        movimientos = [{"fecha": "2026-10-01", "concepto": "COMPRA TIENDA", "importe": -9.99, "categoria": "Otros"}]
        gastos, _, _ = cuadrar(movimientos, [comprobante("t.jpg", "Tienda", "", 9.99, "Otros")])
        self.assertEqual(gastos["Comprobante"].tolist(), ["t.jpg"])


if __name__ == "__main__":
    unittest.main()
