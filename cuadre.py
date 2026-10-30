"""Lógica de cuadre: empareja comprobantes con movimientos del extracto y agrupa por categoría.

Aquí no hay IA: son reglas fijas y comprobables. La IA solo lee los documentos (app.py).

1. Uno a uno, en dos niveles:
   - Seguro: mismo importe (±1 céntimo) y fechas separadas como mucho N días. La fecha del
     comprobante puede ser la de emisión o la de vencimiento (un débito automático se cobra el día
     que vence la factura): vale la más cercana.
   - Por confirmar: si no es seguro, pero el nombre se parece mucho (el del comercio o el del
     archivo) y el importe es parecido (±10 %) o las fechas están a menos de un mes. Se empareja
     y el usuario confirma con un botón si es correcto (o lo descarta).
   Si hay varios candidatos, gana el de fecha más cercana y nombre más parecido.
   En Uruguay, un servicio pagado por débito automático tiene 2 puntos menos de IVA: el banco
   cobra el total menos el 2 % de la parte gravada. También es «seguro» (ver importes_con_descuento).
2. Reembolsos agrupados: alguien paga varias compras y luego se le transfiere el total.
   Para cada gasto sin comprobante se busca una combinación de 2 o más comprobantes sueltos,
   anteriores al pago, que sumen exactamente su importe.
"""

import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

import pandas as pd

CATEGORIAS = [
    "Alimentación",
    "Restauración",
    "Transporte y combustible",
    "Suministros (luz, agua, gas)",
    "Telecomunicaciones y software",
    "Material y oficina",
    "Salud",
    "Impuestos y cuotas",
    "Compras online",
    "Otros",
]

# Palabras que no ayudan a comparar nombres: las típicas del banco, las de los nombres de archivo
# y las muy cortas («de», «la»…)
RUIDO = {
    "compra", "tarj", "tarjeta", "pago", "adeudo", "recibo", "bizum", "transf", "trf", "sl", "sa", "s.l.", "s.a.",
    "db", "deb", "aut", "debito", "automatico", "e-brou", "brou", "otros", "servicios", "comercio",
    "factura", "ticket", "pdf", "jpg", "jpeg", "png", "webp", "heic",
    "de", "del", "la", "las", "el", "los", "y", "a", "en",
}

# Uruguay: un servicio pagado por débito automático tiene 2 puntos menos de IVA (22 % → 20 %, 10 % → 8 %).
# Es decir, se descuenta el 2 % de la parte gravada (la base, sin IVA).
PAISES = ["España", "Uruguay"]
TIPOS_IVA_UY = [22, 10]  # si no se ha leído la base, se supone todo gravado a uno de los dos
PUNTOS_DESCUENTO_IVA = 2
CATEGORIAS_SERVICIOS = {"Suministros (luz, agua, gas)", "Telecomunicaciones y software"}
# «DEBITO AUTOMATICO», «DEB. AUTOMATICO», «DEB AUT», «DB AUT», «DB. AUT»… (ya en minúsculas y sin tildes)
DEBITO_AUTOMATICO = re.compile(r"\b(deb(ito)?|db)\W*aut(omatico)?\b")
# El banco puede redondear el IVA de otra forma que nosotros: se admiten 2 céntimos
MARGEN_DESCUENTO = 0.02

# Emparejamientos «por confirmar»
PARECIDO_NOMBRE = 0.6  # a partir de aquí, el nombre se considera el mismo
MARGEN_IMPORTE = 0.10  # importe parecido: ±10 %
DIAS_POR_CONFIRMAR = 35  # fechas a como mucho un mes (una factura mensual)
POR_CONFIRMAR = "🟡 Por confirmar"


def normalizar(texto):
    """Minúsculas, sin tildes y sin palabras de ruido."""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    palabras = [p.strip(".,*-/:()") for p in texto.replace("_", " ").split()]
    return " ".join(p for p in palabras if p and p not in RUIDO and not p.isdigit())


def parecido(a, b):
    """Parecido entre dos nombres, de 0 a 1. Si comparten una palabra de 3+ letras, al menos 0.6.

    Con 3 letras ya cuentan las siglas («UTE», «OSE»); las palabras cortas sin sentido están en RUIDO.
    """
    a, b = normalizar(a), normalizar(b)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    comunes = {p for p in a.split() if len(p) >= 3} & {p for p in b.split() if len(p) >= 3}
    return max(ratio, PARECIDO_NOMBRE) if comunes else ratio


def parecido_comprobante(comp, concepto):
    """Cuánto se parece el comprobante al concepto del banco: por el comercio o por el nombre del archivo.

    El nombre del archivo ayuda mucho: «UTE - Factura.pdf» frente a un comercio leído como
    «Administración Nacional de Usinas…», o una foto llamada como el asunto de una transferencia.
    """
    nombre_archivo = str(comp["archivo"]).rsplit(".", 1)[0]
    return max(parecido(comp["comercio"], concepto), parecido(nombre_archivo, concepto))


def leer_fecha(valor):
    """Convierte 'AAAA-MM-DD' en fecha. Devuelve None si no se puede."""
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def dias_entre(mov, comp):
    """Días entre el gasto y el comprobante, con su fecha o con su vencimiento: la más cercana.

    Devuelve None si no se puede saber (el comprobante no tiene fechas legibles).
    """
    f_mov = leer_fecha(mov["fecha"])
    fechas = [leer_fecha(comp.get(campo, "")) for campo in ("fecha", "vencimiento")]
    dias = [abs((f_mov - f).days) for f in fechas if f and f_mov]
    return min(dias) if dias else None


def normalizar_categoria(categoria):
    return categoria if categoria in CATEGORIAS else "Otros"


def es_debito_automatico(concepto):
    """True si el concepto del banco dice que es un débito automático."""
    texto = unicodedata.normalize("NFKD", str(concepto)).encode("ascii", "ignore").decode().lower()
    return bool(DEBITO_AUTOMATICO.search(texto))


def importes_con_descuento(comp):
    """Lo que cobra el banco por esta factura con 2 puntos menos de IVA (Uruguay, débito automático).

    Se descuenta el 2 % de la base gravada. Ejemplo: total 2.378,00 con 1.707,98 gravados
    → 2.378,00 − 34,16 = 2.343,84. Si la IA no ha leído la base, se supone todo gravado al 22 %
    o al 10 % y se devuelven los dos importes posibles.
    """
    total, base = comp["total"], comp.get("base_gravada") or 0
    bases = [base] if base > 0 else [total / (1 + tipo / 100) for tipo in TIPOS_IVA_UY]
    return [round(total - b * PUNTOS_DESCUENTO_IVA / 100, 2) for b in bases]


def como_encaja_importe(mov, comp, pais):
    """Compara lo que cobró el banco con el total del comprobante.

    Devuelve "exacto" (±1 céntimo), "descuento" (Uruguay: débito automático de un servicio con
    2 puntos menos de IVA), "parecido" (±10 %) o None si no se parecen.
    """
    cobrado = abs(mov["importe"])
    if abs(cobrado - comp["total"]) <= 0.01:
        return "exacto"
    if (pais == "Uruguay" and es_debito_automatico(mov["concepto"])
            and normalizar_categoria(comp["categoria"]) in CATEGORIAS_SERVICIOS
            and any(abs(cobrado - d) <= MARGEN_DESCUENTO for d in importes_con_descuento(comp))):
        return "descuento"
    if abs(cobrado - comp["total"]) <= MARGEN_IMPORTE * comp["total"]:
        return "parecido"
    return None


def clave_pareja(fecha, concepto, importe, archivo):
    """Identifica un gasto del banco con un comprobante, para recordar lo que confirma o descarta el usuario.

    Se forma con lo que sale en la tabla de gastos, así que la app la puede rehacer desde una fila.
    """
    return f"{fecha}|{concepto}|{abs(float(importe)):.2f}|{archivo}"


def motivo_duda(cobrado, comp, como, dias, tolerancia_dias):
    """Por qué un emparejamiento está «por confirmar», en palabras sencillas."""
    partes = ["mismo nombre"]
    if como == "parecido":
        partes.append(f"el importe no coincide (diferencia de {abs(cobrado - comp['total']):.2f})".replace(".", ","))
    if dias is None:
        partes.append("el comprobante no tiene fecha")
    elif dias > tolerancia_dias:
        partes.append(f"{dias} días entre las fechas")
    return ", ".join(partes)


def emparejar(movimientos, comprobantes, tolerancia_dias=4, pais="España", confirmados=(), rechazados=()):
    """Empareja cada comprobante con como mucho un gasto del extracto (y viceversa).

    movimientos: lista de dict con fecha, concepto, importe (gasto en negativo), categoria.
    comprobantes: lista de dict con archivo, comercio, fecha, total, categoria, legible
                  y, si se han leído, vencimiento y base_gravada.
    pais: con "Uruguay" se aplica el descuento de IVA por débito automático.
    confirmados / rechazados: claves de clave_pareja que el usuario ha confirmado o descartado.
    Devuelve (pares, dudas): pares = {indice_movimiento: indice_comprobante};
    dudas = {indice_movimiento: motivo} para los que están «por confirmar».
    """
    candidatos = []
    for i_mov, mov in enumerate(movimientos):
        if mov["importe"] >= 0:  # solo gastos
            continue
        cobrado = abs(mov["importe"])
        for i_comp, comp in enumerate(comprobantes):
            if not comp.get("legible", True) or comp["total"] <= 0:
                continue
            clave = clave_pareja(mov["fecha"], mov["concepto"], mov["importe"], comp["archivo"])
            if clave in rechazados:
                continue
            como = como_encaja_importe(mov, comp, pais)
            dias = dias_entre(mov, comp)
            # Sin fecha legible en el ticket: se acepta por importe, pero con penalización
            distancia = tolerancia_dias if dias is None else dias
            nombre = parecido_comprobante(comp, mov["concepto"])
            if clave in confirmados:
                nivel, motivo = 0, None
            elif como in ("exacto", "descuento") and distancia <= tolerancia_dias:
                nivel, motivo = 1, None
            elif como and nombre >= PARECIDO_NOMBRE and distancia <= DIAS_POR_CONFIRMAR:
                nivel, motivo = 2, motivo_duda(cobrado, comp, como, dias, tolerancia_dias)
            else:
                continue
            # Dentro de cada nivel: fecha cercana y nombre parecido. Un importe exacto gana a uno con
            # descuento, y este a uno solo parecido.
            puntuacion = distancia - 5 * nombre + {"exacto": 0, "descuento": 1, "parecido": 3}.get(como, 0)
            candidatos.append((nivel, puntuacion, i_mov, i_comp, motivo))

    # Primero los confirmados, luego los seguros y al final los dudosos;
    # cada movimiento y cada comprobante se usan una sola vez
    pares, dudas, usados = {}, {}, set()
    for _, _, i_mov, i_comp, motivo in sorted(candidatos, key=lambda c: c[:4]):
        if i_mov not in pares and i_comp not in usados:
            pares[i_mov] = i_comp
            usados.add(i_comp)
            if motivo:
                dudas[i_mov] = motivo
    return pares, dudas


def a_centimos(euros):
    """Trabajamos en céntimos enteros para que 0.1 + 0.2 sume exactamente 0.3."""
    return round(abs(euros) * 100)


def buscar_combinaciones(objetivo, candidatos, max_soluciones=2, max_pasos=200_000):
    """Busca combinaciones de 2+ comprobantes cuyos importes (en céntimos) sumen el objetivo.

    candidatos: lista de (indice_comprobante, centimos).
    Devuelve hasta max_soluciones listas de índices (si hay 2, el resultado es ambiguo).
    """
    candidatos = sorted(candidatos, key=lambda c: -c[1])
    # resto[k] = suma de los candidatos desde k: si no llega al objetivo, no merece seguir
    resto = [sum(c for _, c in candidatos[k:]) for k in range(len(candidatos) + 1)]
    soluciones, pasos = [], 0

    def probar(k, falta, elegidos):
        nonlocal pasos
        pasos += 1
        if len(soluciones) >= max_soluciones or pasos > max_pasos:
            return
        if falta == 0:
            if len(elegidos) >= 2:
                soluciones.append(list(elegidos))
            return
        if k == len(candidatos) or resto[k] < falta:
            return
        indice, centimos = candidatos[k]
        if centimos <= falta:
            probar(k + 1, falta - centimos, elegidos + [indice])
        probar(k + 1, falta, elegidos)

    probar(0, objetivo, [])
    return soluciones


def agrupar_reembolsos(movimientos, comprobantes, pares, tolerancia_dias=4, ventana_dias=30):
    """Para los gastos sin comprobante, busca varios comprobantes sueltos que sumen su importe.

    Solo se usan comprobantes con fecha entre `ventana_dias` antes del pago y `tolerancia_dias` después.
    Devuelve dict {indice_movimiento: (lista_indices_comprobante, ambiguo)}.
    """
    usados = set(pares.values())
    grupos = {}
    sin_comprobante = [i for i, m in enumerate(movimientos) if m["importe"] < 0 and i not in pares]
    # Del más antiguo al más reciente: cada comprobante se usa una sola vez
    for i_mov in sorted(sin_comprobante, key=lambda i: str(movimientos[i]["fecha"])):
        f_mov = leer_fecha(movimientos[i_mov]["fecha"])
        if f_mov is None:
            continue
        candidatos = []
        for i_comp, comp in enumerate(comprobantes):
            f_comp = leer_fecha(comp["fecha"])
            if i_comp in usados or not comp.get("legible", True) or comp["total"] <= 0 or f_comp is None:
                continue
            if -tolerancia_dias <= (f_mov - f_comp).days <= ventana_dias:
                candidatos.append((i_comp, a_centimos(comp["total"])))
        soluciones = buscar_combinaciones(a_centimos(movimientos[i_mov]["importe"]), candidatos)
        if soluciones:
            elegidos = sorted(soluciones[0])
            grupos[i_mov] = (elegidos, len(soluciones) > 1)
            usados.update(elegidos)
    return grupos


def cuadrar(movimientos, comprobantes, tolerancia_dias=4, ventana_reembolso=30, pais="España",
            confirmados=(), rechazados=()):
    """Devuelve (tabla_gastos, resumen_por_categoria, comprobantes_sin_movimiento) como DataFrames.

    En la tabla de gastos, un reembolso agrupado ocupa una fila por comprobante (con el mismo
    n.º de movimiento), para que cada compra sume en su categoría.
    Con ventana_reembolso=0 no se buscan reembolsos agrupados.
    confirmados / rechazados: emparejamientos «por confirmar» que el usuario ya ha revisado (clave_pareja).
    Con pais="Uruguay", un débito automático de un servicio cuadra con 2 puntos menos de IVA.
    """
    pares, dudas = emparejar(movimientos, comprobantes, tolerancia_dias, pais, set(confirmados), set(rechazados))
    grupos = agrupar_reembolsos(movimientos, comprobantes, pares, tolerancia_dias, ventana_reembolso) if ventana_reembolso else {}

    filas = []
    numero = 0
    for i_mov, mov in enumerate(movimientos):
        if mov["importe"] >= 0:
            continue
        numero += 1
        base = {"Mov.": numero, "Fecha": mov["fecha"], "Concepto": mov["concepto"]}
        if i_mov in pares:
            comp = comprobantes[pares[i_mov]]
            clave = clave_pareja(mov["fecha"], mov["concepto"], mov["importe"], comp["archivo"])
            if i_mov in dudas:
                estado = f"{POR_CONFIRMAR}: {dudas[i_mov]}"
            elif clave in confirmados:
                estado = "✅ Con comprobante · confirmado por usted"
            else:
                estado = "✅ Con comprobante"
                if como_encaja_importe(mov, comp, pais) == "descuento":
                    # El importe de la fila es lo que cobró el banco: menos que la factura
                    descuento = round(comp["total"] - abs(mov["importe"]), 2)
                    estado += f" · descuento IVA débito automático ({descuento:.2f})".replace(".", ",")
            filas.append({**base, "Importe (€)": round(abs(mov["importe"]), 2),
                          "Categoría": normalizar_categoria(comp["categoria"]),
                          "Comprobante": comp["archivo"], "Estado": estado})
        elif i_mov in grupos:
            indices, ambiguo = grupos[i_mov]
            for n, i_comp in enumerate(indices, start=1):
                comp = comprobantes[i_comp]
                estado = f"🔗 Reembolso agrupado ({n}/{len(indices)})"
                if ambiguo:
                    estado += " · revisar: hay otra combinación posible"
                filas.append({**base, "Importe (€)": round(comp["total"], 2),
                              "Categoría": normalizar_categoria(comp["categoria"]),
                              "Comprobante": comp["archivo"], "Estado": estado})
        else:
            filas.append({**base, "Importe (€)": round(abs(mov["importe"]), 2),
                          "Categoría": normalizar_categoria(mov["categoria"]),
                          "Comprobante": "", "Estado": "⚠️ Falta comprobante"})
    columnas = ["Mov.", "Fecha", "Concepto", "Importe (€)", "Categoría", "Comprobante", "Estado"]
    gastos = pd.DataFrame(filas, columns=columnas)

    if gastos.empty:
        resumen = pd.DataFrame(columns=["Categoría", "Total (€)", "Gastos", "Con comprobante", "Sin comprobante (€)"])
    else:
        gastos["_justificado"] = gastos["Comprobante"] != ""
        gastos["_sin"] = gastos["Importe (€)"].where(~gastos["_justificado"], 0)
        resumen = (
            gastos.groupby("Categoría")
            .agg(**{
                "Total (€)": ("Importe (€)", "sum"),
                "Gastos": ("Importe (€)", "count"),
                "Con comprobante": ("_justificado", "sum"),
                "Sin comprobante (€)": ("_sin", "sum"),
            })
            .round(2)
            .sort_values("Total (€)", ascending=False)
            .reset_index()
        )
        gastos = gastos.drop(columns=["_justificado", "_sin"])

    usados = set(pares.values()) | {i for indices, _ in grupos.values() for i in indices}
    sueltos = pd.DataFrame(
        [
            {
                "Archivo": c["archivo"],
                "Comercio": c["comercio"],
                "Fecha": c["fecha"],
                "Total (€)": c["total"],
                "Motivo": "No se ha podido leer" if not c.get("legible", True) else "No aparece en el extracto",
            }
            for i, c in enumerate(comprobantes)
            if i not in usados
        ],
        columns=["Archivo", "Comercio", "Fecha", "Total (€)", "Motivo"],
    )
    return gastos, resumen, sueltos


def consultar_gastos(gastos, categoria=None, desde=None, hasta=None, texto=None, justificante=None):
    """Filtra la tabla de gastos de `cuadrar` y suma. La usa la conversación (F5) para que la IA no sume.

    - categoria: una de CATEGORIAS. desde / hasta: 'AAAA-MM-DD', incluidos.
    - texto: se busca (sin tildes ni mayúsculas) en el concepto del banco y en el nombre del comprobante.
    - justificante: "con", "sin" o None (todos).
    Devuelve un dict con el total en euros, el n.º de gastos (un reembolso agrupado cuenta una vez) y las filas.
    """
    filas = gastos
    if categoria:
        filas = filas[filas["Categoría"] == normalizar_categoria(categoria)]
    if desde:
        filas = filas[filas["Fecha"] >= desde]
    if hasta:
        filas = filas[filas["Fecha"] <= hasta]
    if texto and normalizar(texto):
        buscado = normalizar(texto)
        en_concepto = filas["Concepto"].map(normalizar).str.contains(buscado, regex=False)
        en_comprobante = filas["Comprobante"].map(normalizar).str.contains(buscado, regex=False)
        filas = filas[en_concepto | en_comprobante]
    if justificante == "con":
        filas = filas[filas["Comprobante"] != ""]
    elif justificante == "sin":
        filas = filas[filas["Comprobante"] == ""]
    return {
        "total_euros": round(float(filas["Importe (€)"].sum()), 2),
        "numero_de_gastos": int(filas["Mov."].nunique()),
        "filas": filas.to_dict("records"),
    }
