"""Lo que la IA debería leer de los archivos de ejemplos/ (escrito a mano).

Así las pruebas de cuadre.py no gastan cuota: prueban las reglas, no la lectura.
Si cambias ejemplos/generar_ejemplos.py, actualiza también estos datos.
"""

MOVIMIENTOS = [
    {"fecha": "2026-10-01", "concepto": "CUOTA REGIMEN ESPECIAL AUTONOMOS", "importe": -230.00, "categoria": "Impuestos y cuotas"},
    {"fecha": "2026-10-02", "concepto": "TRANSF RECIBIDA CLIENTE ESTUDIO NORTE", "importe": 1200.00, "categoria": "Otros"},
    {"fecha": "2026-10-04", "concepto": "COMPRA TARJ. 4444 SUPERM EL ROBLE", "importe": -46.37, "categoria": "Alimentación"},
    {"fecha": "2026-10-06", "concepto": "COMPRA TARJ. 4444 GASOLINERA RUTA 5", "importe": -60.00, "categoria": "Transporte y combustible"},
    {"fecha": "2026-10-08", "concepto": "ADEUDO NUBEDISENO SOFTWARE", "importe": -24.19, "categoria": "Telecomunicaciones y software"},
    {"fecha": "2026-10-10", "concepto": "COMPRA TARJ. 4444 CAFETERIA LA PLAZA", "importe": -12.80, "categoria": "Restauración"},
    {"fecha": "2026-10-14", "concepto": "RECIBO ELECTRICA DEL VALLE", "importe": -68.45, "categoria": "Suministros (luz, agua, gas)"},
    {"fecha": "2026-10-17", "concepto": "COMPRA TARJ. 4444 MEGAMARKET ONLINE", "importe": -35.99, "categoria": "Compras online"},
    {"fecha": "2026-10-22", "concepto": "COMPRA TARJ. 4444 PAPELERIA EL LAPIZ", "importe": -18.50, "categoria": "Material y oficina"},
    {"fecha": "2026-10-24", "concepto": "COMPRA TARJ. 4444 CAFETERIA LA PLAZA", "importe": -12.80, "categoria": "Restauración"},
    {"fecha": "2026-10-28", "concepto": "TRANSF EMITIDA A MARTA INVENTADA REEMBOLSO COMPRAS", "importe": -51.65, "categoria": "Otros"},
]


def comprobante(archivo, comercio, fecha, total, categoria, legible=True):
    return {"archivo": archivo, "comercio": comercio, "fecha": fecha, "total": total,
            "categoria": categoria, "legible": legible}


COMPROBANTES = [
    comprobante("factura_luz.pdf", "ELÉCTRICA DEL VALLE S.A.", "2026-10-12", 68.45, "Suministros (luz, agua, gas)"),
    comprobante("factura_software.pdf", "NUBEDISEÑO SOFTWARE S.L.", "2026-10-08", 24.19, "Telecomunicaciones y software"),
    comprobante("reembolso_copisteria.jpg", "COPISTERIA RAPIDA", "2026-10-25", 12.50, "Material y oficina"),
    comprobante("reembolso_ferreteria.jpg", "FERRETERIA LA LLAVE", "2026-10-15", 23.45, "Material y oficina"),
    comprobante("reembolso_fruteria.jpg", "FRUTERIA HERMANOS VERDE", "2026-10-20", 15.70, "Alimentación"),
    comprobante("ticket_cafeteria.jpg", "CAFETERIA LA PLAZA", "2026-10-10", 12.80, "Restauración"),
    comprobante("ticket_gasolinera.jpg", "GASOLINERA RUTA 5", "2026-10-05", 60.00, "Transporte y combustible"),
    comprobante("ticket_papeleria.jpg", "PAPELERIA EL LAPIZ", "2026-10-21", 18.50, "Material y oficina"),
    comprobante("ticket_restaurante_efectivo.jpg", "RESTAURANTE EL MOLINO", "2026-10-19", 27.40, "Restauración"),
    comprobante("ticket_supermercado.jpg", "SUPERMERCADO EL ROBLE", "2026-10-03", 46.37, "Alimentación"),
]
