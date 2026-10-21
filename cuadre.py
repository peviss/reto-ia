"""Lógica de cuadre: empareja comprobantes con movimientos del extracto y agrupa por categoría.

Aquí no hay IA: son reglas fijas y comprobables. La IA solo lee los documentos (app.py).

1. Uno a uno: mismo importe (±1 céntimo) y fechas separadas como mucho N días.
   Si hay varios candidatos, gana el de fecha más cercana y nombre más parecido.
2. Reembolsos agrupados: alguien paga varias compras y luego se le transfiere el total.
   Para cada gasto sin comprobante se busca una combinación de 2 o más comprobantes sueltos,
   anteriores al pago, que sumen exactamente su importe.
"""

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

# Palabras típicas de los conceptos bancarios que no ayudan a comparar nombres
RUIDO = {"compra", "tarj", "tarjeta", "pago", "adeudo", "recibo", "bizum", "transf", "sl", "sa", "s.l.", "s.a."}


def normalizar(texto):
    """Minúsculas, sin tildes y sin palabras de ruido bancario."""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    palabras = [p.strip(".,*-/") for p in texto.split()]
    return " ".join(p for p in palabras if p and p not in RUIDO and not p.isdigit())


def parecido(a, b):
    """Parecido entre dos nombres, de 0 a 1. Si comparten una palabra de 4+ letras, al menos 0.6."""
    a, b = normalizar(a), normalizar(b)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    comunes = {p for p in a.split() if len(p) >= 4} & {p for p in b.split() if len(p) >= 4}
    return max(ratio, 0.6) if comunes else ratio


def leer_fecha(valor):
    """Convierte 'AAAA-MM-DD' en fecha. Devuelve None si no se puede."""
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def normalizar_categoria(categoria):
    return categoria if categoria in CATEGORIAS else "Otros"


def emparejar(movimientos, comprobantes, tolerancia_dias=4):
    """Empareja cada comprobante con como mucho un gasto del extracto (y viceversa).

    movimientos: lista de dict con fecha, concepto, importe (gasto en negativo), categoria.
    comprobantes: lista de dict con archivo, comercio, fecha, total, categoria, legible.
    Devuelve dict {indice_movimiento: indice_comprobante}.
    """
    candidatos = []
    for i_mov, mov in enumerate(movimientos):
        if mov["importe"] >= 0:  # solo gastos
            continue
        f_mov = leer_fecha(mov["fecha"])
        for i_comp, comp in enumerate(comprobantes):
            if not comp.get("legible", True) or comp["total"] <= 0:
                continue
            if abs(abs(mov["importe"]) - comp["total"]) > 0.01:
                continue
            f_comp = leer_fecha(comp["fecha"])
            # Sin fecha legible en el ticket: se acepta por importe, pero con penalización
            dias = abs((f_mov - f_comp).days) if f_mov and f_comp else tolerancia_dias
            if dias > tolerancia_dias:
                continue
            puntuacion = dias - 5 * parecido(comp["comercio"], mov["concepto"])
            candidatos.append((puntuacion, i_mov, i_comp))

    # Primero las parejas más claras; cada movimiento y cada comprobante se usan una sola vez
    pares = {}
    usados = set()
    for _, i_mov, i_comp in sorted(candidatos):
        if i_mov not in pares and i_comp not in usados:
            pares[i_mov] = i_comp
            usados.add(i_comp)
    return pares


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


def cuadrar(movimientos, comprobantes, tolerancia_dias=4, ventana_reembolso=30):
    """Devuelve (tabla_gastos, resumen_por_categoria, comprobantes_sin_movimiento) como DataFrames.

    En la tabla de gastos, un reembolso agrupado ocupa una fila por comprobante (con el mismo
    n.º de movimiento), para que cada compra sume en su categoría.
    Con ventana_reembolso=0 no se buscan reembolsos agrupados.
    """
    pares = emparejar(movimientos, comprobantes, tolerancia_dias)
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
            filas.append({**base, "Importe (€)": round(abs(mov["importe"]), 2),
                          "Categoría": normalizar_categoria(comp["categoria"]),
                          "Comprobante": comp["archivo"], "Estado": "✅ Con comprobante"})
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
