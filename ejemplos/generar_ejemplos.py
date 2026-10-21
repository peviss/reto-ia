"""Genera los datos de ejemplo de la app: un extracto bancario y comprobantes INVENTADOS.

Uso:  python ejemplos/generar_ejemplos.py
Todos los nombres, NIF, cuentas e importes son ficticios.

Casos que cubren:
- Tickets que cuadran con el extracto (algunos con la fecha del banco 1-2 días después).
- Un gasto con comprobante en PDF (factura).
- Gastos sin comprobante (cuota de autónomos, compra online).
- Un ticket pagado en efectivo que no está en el extracto.
- Dos gastos con el mismo importe en fechas distintas (la fecha decide).
- Un reembolso: una socia adelanta 3 compras y luego se le transfiere el total (51,65 €).
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CARPETA = Path(__file__).parent

EXTRACTO = """Fecha operación;Fecha valor;Concepto;Importe;Saldo
01/10/2026;01/10/2026;CUOTA REGIMEN ESPECIAL AUTONOMOS;-230,00;2.140,55
02/10/2026;02/10/2026;TRANSF RECIBIDA CLIENTE ESTUDIO NORTE;1.200,00;3.340,55
04/10/2026;03/10/2026;COMPRA TARJ. 4444 SUPERM EL ROBLE;-46,37;3.294,18
06/10/2026;05/10/2026;COMPRA TARJ. 4444 GASOLINERA RUTA 5;-60,00;3.234,18
08/10/2026;08/10/2026;ADEUDO NUBEDISENO SOFTWARE;-24,19;3.209,99
10/10/2026;10/10/2026;COMPRA TARJ. 4444 CAFETERIA LA PLAZA;-12,80;3.197,19
14/10/2026;14/10/2026;RECIBO ELECTRICA DEL VALLE;-68,45;3.128,74
17/10/2026;17/10/2026;COMPRA TARJ. 4444 MEGAMARKET ONLINE;-35,99;3.092,75
22/10/2026;21/10/2026;COMPRA TARJ. 4444 PAPELERIA EL LAPIZ;-18,50;3.074,25
24/10/2026;24/10/2026;COMPRA TARJ. 4444 CAFETERIA LA PLAZA;-12,80;3.061,45
28/10/2026;28/10/2026;TRANSF EMITIDA A MARTA INVENTADA REEMBOLSO COMPRAS;-51,65;3.009,80
"""

TICKETS = {
    "ticket_supermercado.jpg": [
        "SUPERMERCADO EL ROBLE", "C/ Inventada 12, Villanueva", "NIF B00000001", "",
        "FECHA: 03/10/2026  18:21", "--------------------------------",
        "LECHE ENTERA 6L          5,94", "PAN BARRA x2             1,80", "TOMATE KG                3,12",
        "ACEITE OLIVA 1L          8,95", "CAFE MOLIDO              4,25", "PRODUCTOS LIMPIEZA      12,40",
        "FRUTA VARIADA            9,91", "--------------------------------",
        "TOTAL                   46,37 EUR", "PAGO TARJETA ****4444", "", "*** EJEMPLO FICTICIO ***",
    ],
    "ticket_gasolinera.jpg": [
        "GASOLINERA RUTA 5", "Ctra. Ficticia km 5", "NIF B00000002", "",
        "05/10/2026   09:02", "SURTIDOR 3  SIN PLOMO 95", "LITROS: 36,59   1,639 EUR/L",
        "--------------------------------", "IMPORTE TOTAL           60,00 EUR",
        "IVA 21% INCLUIDO", "TARJETA ****4444", "", "*** EJEMPLO FICTICIO ***",
    ],
    "ticket_cafeteria.jpg": [
        "CAFETERIA LA PLAZA", "Plaza Mayor 1", "NIF B00000003", "",
        "Fecha 10/10/2026  13:45", "Mesa 4", "2 MENU DEL DIA           12,80",
        "--------------------------------", "TOTAL                   12,80",
        "Tarjeta", "Gracias por su visita", "", "*** EJEMPLO FICTICIO ***",
    ],
    "ticket_papeleria.jpg": [
        "PAPELERIA EL LAPIZ", "C/ Escuela 7", "NIF B00000004", "",
        "21/10/2026", "CUADERNO A4 x3            7,50", "BOLIGRAFOS PACK 10        4,20",
        "CARTUCHO TINTA            6,80", "--------------------------------",
        "TOTAL A PAGAR            18,50", "TARJ ****4444", "", "*** EJEMPLO FICTICIO ***",
    ],
    "ticket_restaurante_efectivo.jpg": [
        "RESTAURANTE EL MOLINO", "Camino del Rio 3", "NIF B00000005", "",
        "19/10/2026  14:30", "COMIDA CLIENTE 2 PAX     27,40", "--------------------------------",
        "TOTAL                   27,40", "EFECTIVO                30,00", "CAMBIO                   2,60",
        "", "*** EJEMPLO FICTICIO ***",
    ],
    # Compras que adelantó Marta (socia) y que se le reembolsan juntas el 28/10
    "reembolso_ferreteria.jpg": [
        "FERRETERIA LA LLAVE", "Av. Imaginaria 22", "NIF B00000008", "",
        "15/10/2026  11:10", "BOMBILLAS LED x4           9,96", "CINTA AMERICANA            4,50",
        "ALARGADOR 3 TOMAS          8,99", "--------------------------------",
        "TOTAL                     23,45", "TARJETA ****9999", "", "*** EJEMPLO FICTICIO ***",
    ],
    "reembolso_fruteria.jpg": [
        "FRUTERIA HERMANOS VERDE", "Mercado Central, puesto 4", "NIF B00000009", "",
        "20/10/2026", "MANZANAS 2KG               4,20", "NARANJAS 3KG               5,85",
        "PLATANOS 1KG               2,15", "AGUA 6x1,5L                3,50",
        "--------------------------------", "TOTAL                     15,70", "EFECTIVO", "",
        "*** EJEMPLO FICTICIO ***",
    ],
    "reembolso_copisteria.jpg": [
        "COPISTERIA RAPIDA", "C/ Imprenta 5", "NIF B00000010", "",
        "25/10/2026  17:40", "COPIAS COLOR A4 x50       10,00", "ENCUADERNACION             2,50",
        "--------------------------------", "TOTAL                     12,50", "BIZUM", "",
        "*** EJEMPLO FICTICIO ***",
    ],
}

FACTURAS = {
    "factura_software.pdf": [
        "NUBEDISEÑO SOFTWARE S.L.", "CIF B00000006 · Calle Nube 9, Madrid", "",
        "FACTURA N.º ND-2026-10-5521", "Fecha de factura: 08/10/2026", "",
        "Cliente: Laura Ejemplo (diseño gráfico)", "NIF cliente: 00000000T", "",
        "Concepto                                   Importe",
        "Suscripción mensual Plan Diseño Pro          19,99 €",
        "IVA 21 %                                      4,20 €",
        "TOTAL FACTURA                                24,19 €", "",
        "Forma de pago: domiciliación bancaria", "", "*** DOCUMENTO DE EJEMPLO FICTICIO ***",
    ],
    "factura_luz.pdf": [
        "ELÉCTRICA DEL VALLE S.A.", "CIF A00000007", "",
        "FACTURA DE ELECTRICIDAD", "N.º factura: EV-778812", "Fecha de emisión: 12/10/2026",
        "Periodo: 01/09/2026 - 30/09/2026", "Titular: Laura Ejemplo", "",
        "Potencia contratada (4,6 kW)                  18,40 €",
        "Energía consumida (210 kWh)                   34,20 €",
        "Impuesto eléctrico                             2,67 €",
        "Alquiler de equipos                            1,30 €",
        "IVA 21 %                                      11,88 €",
        "TOTAL A PAGAR                                 68,45 €", "",
        "Se cargará en su cuenta el 14/10/2026", "", "*** DOCUMENTO DE EJEMPLO FICTICIO ***",
    ],
}


def fuente(tamano):
    return ImageFont.load_default(size=tamano)


def dibujar_ticket(lineas, destino):
    """Ticket estrecho, papel ligeramente gris y un poco girado, como una foto de móvil."""
    ancho, alto_linea = 520, 30
    papel = Image.new("RGB", (ancho, 60 + alto_linea * len(lineas)), (248, 246, 240))
    dibujo = ImageDraw.Draw(papel)
    for n, linea in enumerate(lineas):
        dibujo.text((30, 30 + n * alto_linea), linea, fill=(30, 30, 30), font=fuente(22))
    foto = Image.new("RGB", (papel.width + 160, papel.height + 160), (90, 80, 70))
    foto.paste(papel, (80, 80))
    foto = foto.rotate(random.uniform(-3, 3), expand=True, fillcolor=(90, 80, 70))
    foto.save(destino, "JPEG", quality=85)


def dibujar_factura(lineas, destino):
    """Página A4 (150 ppp) guardada como PDF."""
    pagina = Image.new("RGB", (1240, 1754), "white")
    dibujo = ImageDraw.Draw(pagina)
    dibujo.rectangle((80, 80, 1160, 90), fill=(40, 70, 140))
    for n, linea in enumerate(lineas):
        tamano = 40 if n == 0 else 28
        dibujo.text((100, 130 + n * 48), linea, fill=(20, 20, 20), font=fuente(tamano))
    pagina.save(destino, "PDF", resolution=150)


if __name__ == "__main__":
    random.seed(7)
    (CARPETA / "extracto_octubre.csv").write_text(EXTRACTO, encoding="utf-8")
    for nombre, lineas in TICKETS.items():
        dibujar_ticket(lineas, CARPETA / nombre)
    for nombre, lineas in FACTURAS.items():
        dibujar_factura(lineas, CARPETA / nombre)
    print(f"Ejemplos generados en {CARPETA}")
