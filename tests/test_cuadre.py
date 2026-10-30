"""Pruebas de las reglas de cuadre.py con los datos de ejemplo (sin IA).

Cada prueba lleva en el nombre el criterio de aceptación (CA) de ESPECIFICACION §5 que comprueba.
Ejecutar:  python -m unittest discover -s tests -v
"""

import copy
import unittest

from cuadre import clave_pareja, consultar_gastos, cuadrar
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
        # La gasolinera (ticket 05/10, banco 06/10) ya no es segura: mismo nombre, queda por confirmar
        self.assertTrue(fila(gastos, "GASOLINERA")["Estado"].iloc[0].startswith("🟡 Por confirmar"))
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

    def test_CA8_solo_con_el_extracto(self):
        # Sin tickets: todos los gastos salen sin comprobante, pero se agrupan por categoría
        gastos, resumen, sueltos = cuadrar(copy.deepcopy(MOVIMIENTOS), [])
        self.assertEqual(gastos["Mov."].nunique(), 10)
        self.assertEqual(set(gastos["Estado"]), {"⚠️ Falta comprobante"})
        self.assertAlmostEqual(resumen["Total (€)"].sum(), gastos["Importe (€)"].sum(), places=2)
        self.assertTrue(sueltos.empty)

    def test_categoria_inventada_pasa_a_otros(self):
        movimientos = [{"fecha": "2026-10-01", "concepto": "X", "importe": -5.0, "categoria": "Ocio"}]
        gastos, _, _ = cuadrar(movimientos, [])
        self.assertEqual(gastos["Categoría"].tolist(), ["Otros"])

    def test_ticket_sin_fecha_cuadra_por_importe(self):
        movimientos = [{"fecha": "2026-10-01", "concepto": "COMPRA TIENDA", "importe": -9.99, "categoria": "Otros"}]
        gastos, _, _ = cuadrar(movimientos, [comprobante("t.jpg", "Tienda", "", 9.99, "Otros")])
        self.assertEqual(gastos["Comprobante"].tolist(), ["t.jpg"])


def debito(concepto, importe, categoria="Suministros (luz, agua, gas)"):
    """Un gasto del extracto del 10/10 (para las pruebas de Uruguay)."""
    return [{"fecha": "2026-10-10", "concepto": concepto, "importe": importe, "categoria": categoria}]


class DescuentoIvaUruguay(unittest.TestCase):
    """Uruguay: un servicio pagado por débito automático tiene 2 puntos menos de IVA (CA27)."""

    def test_CA27_iva_basico(self):
        # 1.220 = 1.000 + 22 % → con el 20 %, el banco cobra 1.200
        factura = comprobante("luz.pdf", "ELECTRICA DEL SUR", "2026-10-08", 1220.00, "Suministros (luz, agua, gas)")
        gastos, _, sueltos = cuadrar(debito("DEBITO AUTOMATICO ELECTRICA DEL SUR", -1200.00), [factura], pais="Uruguay")
        self.assertEqual(gastos["Comprobante"].tolist(), ["luz.pdf"])
        self.assertIn("descuento IVA débito automático (20,00)", gastos["Estado"][0])
        self.assertEqual(gastos["Importe (€)"].tolist(), [1200.00])  # lo que se pagó de verdad
        self.assertTrue(sueltos.empty)

    def test_CA27_iva_minimo_y_concepto_abreviado(self):
        # 1.100 = 1.000 + 10 % → con el 8 %, el banco cobra 1.080
        factura = comprobante("agua.pdf", "AGUAS DEL LLANO", "2026-10-08", 1100.00, "Suministros (luz, agua, gas)")
        gastos, _, _ = cuadrar(debito("DEB. AUT. AGUAS DEL LLANO", -1080.00), [factura], pais="Uruguay")
        self.assertEqual(gastos["Comprobante"].tolist(), ["agua.pdf"])

    def test_CA27_en_espana_no_se_aplica(self):
        factura = comprobante("luz.pdf", "ELECTRICA DEL SUR", "2026-10-08", 1220.00, "Suministros (luz, agua, gas)")
        gastos, _, _ = cuadrar(debito("DEBITO AUTOMATICO ELECTRICA DEL SUR", -1200.00), [factura])
        # Sin el descuento no es seguro; por el nombre, queda para que el usuario lo confirme
        self.assertTrue(gastos["Estado"][0].startswith("🟡 Por confirmar"))

    def test_CA27_sin_debito_automatico_no_se_aplica(self):
        factura = comprobante("luz.pdf", "ELECTRICA DEL SUR", "2026-10-08", 1220.00, "Suministros (luz, agua, gas)")
        gastos, _, _ = cuadrar(debito("COMPRA TARJ. 4444 ELECTRICA DEL SUR", -1200.00), [factura], pais="Uruguay")
        self.assertTrue(gastos["Estado"][0].startswith("🟡 Por confirmar"))

    def test_CA27_solo_servicios(self):
        ticket = comprobante("cena.jpg", "RESTAURANTE EL MOLINO", "2026-10-08", 1220.00, "Restauración")
        gastos, _, _ = cuadrar(debito("DEBITO AUTOMATICO RESTAURANTE", -1200.00, "Restauración"), [ticket], pais="Uruguay")
        self.assertTrue(gastos["Estado"][0].startswith("🟡 Por confirmar"))

    def test_CA27_gana_el_importe_exacto(self):
        exacta = comprobante("internet.pdf", "RED INVENTADA", "2026-10-08", 1200.00, "Telecomunicaciones y software")
        con_descuento = comprobante("luz.pdf", "RED INVENTADA", "2026-10-08", 1220.00, "Suministros (luz, agua, gas)")
        gastos, _, sueltos = cuadrar(debito("DEBITO AUTOMATICO RED INVENTADA", -1200.00),
                                     [con_descuento, exacta], pais="Uruguay")
        self.assertEqual(gastos["Comprobante"].tolist(), ["internet.pdf"])
        self.assertEqual(gastos["Estado"].tolist(), ["✅ Con comprobante"])
        self.assertEqual(sueltos["Archivo"].tolist(), ["luz.pdf"])



def gasto(fecha, concepto, importe, categoria="Suministros (luz, agua, gas)"):
    return {"fecha": fecha, "concepto": concepto, "importe": importe, "categoria": categoria}


# Un extracto y facturas como los de un banco de Uruguay (nombres inventados, importes reales de ejemplo):
# las facturas de servicios se cobran el día que vencen y el comercio leído puede ser el nombre legal largo
LUZ = comprobante("UTI - Factura.pdf", "Usinas y Transmisiones Inventadas", "2026-08-24", 3622.00,
                  "Suministros (luz, agua, gas)", vencimiento="2026-09-02", base_gravada=2698.96)
AGUA = comprobante("OSI - Factura.pdf", "Obras Sanitarias Inventadas", "2026-09-04", 2378.00,
                   "Suministros (luz, agua, gas)", vencimiento="2026-09-18", base_gravada=1707.98)
TELEFONO = comprobante("TELCO - Factura.pdf", "TELCO", "2026-09-03", 2138.00,
                       "Telecomunicaciones y software", vencimiento="2026-09-18", base_gravada=1752.42)
EXTRACTO_UY = [
    gasto("2026-09-02", "UTI - DEBITO AUTOMATICO", -3622.00),
    gasto("2026-09-18", "OSI - DB AUT", -2343.84),
    gasto("2026-09-18", "TELCO - TELEFONIA FIJA DB. AUT", -2102.95, "Telecomunicaciones y software"),
]


class FacturasDeServicios(unittest.TestCase):
    """Fecha de vencimiento, nombre del archivo, descuento sobre la base y «por confirmar» (CA28)."""

    def estados(self, movimientos, comprobantes, **ajustes):
        gastos, _, sueltos = cuadrar(copy.deepcopy(movimientos), copy.deepcopy(comprobantes), **ajustes)
        return dict(zip(gastos["Concepto"], gastos["Estado"])), gastos, sueltos

    def test_CA28_uruguay_todo_seguro(self):
        estados, gastos, sueltos = self.estados(EXTRACTO_UY, [LUZ, AGUA, TELEFONO], pais="Uruguay")
        # Luz: mismo importe, cobrada el día que vence (no el de emisión, 9 días antes)
        self.assertEqual(estados["UTI - DEBITO AUTOMATICO"], "✅ Con comprobante")
        # Agua y teléfono: el total menos el 2 % de la base gravada
        self.assertEqual(estados["OSI - DB AUT"], "✅ Con comprobante · descuento IVA débito automático (34,16)")
        self.assertEqual(estados["TELCO - TELEFONIA FIJA DB. AUT"],
                         "✅ Con comprobante · descuento IVA débito automático (35,05)")
        self.assertTrue(sueltos.empty)

    def test_CA28_en_espana_quedan_por_confirmar(self):
        estados, _, _ = self.estados(EXTRACTO_UY, [LUZ, AGUA, TELEFONO])
        self.assertEqual(estados["UTI - DEBITO AUTOMATICO"], "✅ Con comprobante")
        self.assertEqual(estados["OSI - DB AUT"],
                         "🟡 Por confirmar: mismo nombre, el importe no coincide (diferencia de 34,16)")

    def test_CA28_sin_vencimiento_por_el_nombre_del_archivo(self):
        # Una lectura sin vencimiento: 9 días entre fechas; el comercio no se parece, el archivo sí
        luz = {**LUZ, "vencimiento": ""}
        estados, _, _ = self.estados(EXTRACTO_UY[:1], [luz])
        self.assertEqual(estados["UTI - DEBITO AUTOMATICO"], "🟡 Por confirmar: mismo nombre, 9 días entre las fechas")

    def test_CA28_confirmar_y_descartar(self):
        clave = clave_pareja("2026-09-18", "OSI - DB AUT", -2343.84, "OSI - Factura.pdf")
        estados, _, _ = self.estados(EXTRACTO_UY[1:2], [AGUA], confirmados={clave})
        self.assertEqual(estados["OSI - DB AUT"], "✅ Con comprobante · confirmado por usted")
        estados, _, sueltos = self.estados(EXTRACTO_UY[1:2], [AGUA], rechazados={clave})
        self.assertEqual(estados["OSI - DB AUT"], "⚠️ Falta comprobante")
        self.assertEqual(sueltos["Archivo"].tolist(), ["OSI - Factura.pdf"])

    def test_CA28_transferencia_por_el_asunto(self):
        # La foto se llama como el asunto de la transferencia, y la compra fue 13 días antes
        foto = comprobante("bolsas servilletas.jpg", "Distribuidora Inventada", "2026-09-15", 1068.00, "Material y oficina")
        movimiento = gasto("2026-09-28", "TRF. E-BROU OTROS - PROVEEDOR INVENTADO - Bolsas Servilletas", -1068.00)
        estados, _, _ = self.estados([movimiento], [foto])
        self.assertTrue(estados[movimiento["concepto"]].startswith("🟡 Por confirmar: mismo nombre, 13 días"))

    def test_CA28_sin_nombre_parecido_no_se_empareja(self):
        # Importe parecido y fechas cercanas, pero nada en común: no se adivina
        ticket = comprobante("ticket.jpg", "Ferreteria Inventada", "2026-09-18", 2300.00, "Material y oficina")
        estados, _, _ = self.estados(EXTRACTO_UY[1:2], [ticket])
        self.assertEqual(estados["OSI - DB AUT"], "⚠️ Falta comprobante")


if __name__ == "__main__":
    unittest.main()
