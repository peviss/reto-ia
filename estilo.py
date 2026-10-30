"""Aspecto de la app: estilos CSS y piezas de HTML que Streamlit no trae (marca, títulos de tarjeta).

Los colores base, la letra y los bordes están en .streamlit/config.toml (tema claro y oscuro).
Aquí solo va lo que el tema no cubre. Los bloques se localizan por su `key`: Streamlit le pone
al contenedor la clase `st-key-<key>`. Los colores llevan transparencia para verse bien en los dos temas.
Solo es presentación: nada de aquí cambia los datos ni el cuadre.
"""

from html import escape

import streamlit as st

import almacen

CSS = """
<style>
/* ---------- General ---------- */
.block-container { max-width: 1180px; padding-top: 2.2rem; }
[data-testid="stHeader"] { background: transparent; }
h1, h2, h3 { letter-spacing: -0.02em; }

/* ---------- Cabecera ---------- */
.st-key-cabecera {
    background:
        radial-gradient(1200px 300px at 0% 0%, rgba(20, 184, 166, 0.18), transparent 60%),
        radial-gradient(800px 260px at 100% 100%, rgba(99, 102, 241, 0.14), transparent 60%);
    border: 1px solid rgba(20, 184, 166, 0.25);
    border-radius: 1.25rem;
    padding: 1.6rem 1.8rem 1.3rem;
}
.st-key-cabecera h1 { font-size: 2.3rem; padding: 0 0 0.2rem; }
.st-key-cabecera p { font-size: 1.05rem; opacity: 0.85; max-width: 780px; }

@media (max-width: 640px) {
    .st-key-cabecera { padding: 1.2rem; }
    .st-key-cabecera h1 { font-size: 1.8rem; }
}

/* ---------- Tarjetas de subida ---------- */
.st-key-paso_extracto, .st-key-paso_comprobantes {
    background: rgba(128, 128, 128, 0.04);
}
.titulo-tarjeta { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.15rem; }
.titulo-tarjeta .icono {
    width: 2.3rem; height: 2.3rem; border-radius: 0.7rem; display: grid; place-items: center;
    font-size: 1.2rem; background: rgba(20, 184, 166, 0.14);
}
.titulo-tarjeta b { font-size: 1.05rem; display: block; }
.titulo-tarjeta span { font-size: 0.82rem; opacity: 0.75; }
[data-testid="stFileUploaderDropzone"] {
    border: 1.5px dashed rgba(20, 184, 166, 0.55) !important;
    background: rgba(20, 184, 166, 0.05) !important;
    transition: background 0.15s ease;
}
[data-testid="stFileUploaderDropzone"]:hover { background: rgba(20, 184, 166, 0.11) !important; }

/* ---------- Botones ---------- */
[data-testid="stBaseButton-primary"] {
    font-weight: 700; box-shadow: 0 6px 18px -8px rgba(15, 118, 110, 0.7);
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
[data-testid="stBaseButton-primary"]:hover { transform: translateY(-1px); box-shadow: 0 10px 22px -10px rgba(15, 118, 110, 0.85); }
.st-key-accion [data-testid="stBaseButton-primary"] { min-height: 3.2rem; font-size: 1.05rem; }

/* ---------- Cifras del resultado ---------- */
[data-testid="stMetric"] { padding: 0.6rem 0.9rem; }
[data-testid="stMetricLabel"] p { font-weight: 600; opacity: 0.8; }

/* ---------- Pestañas como píldoras ---------- */
[data-testid="stTabs"] [role="tablist"] { gap: 0.4rem; flex-wrap: wrap; border-bottom: 0; box-shadow: none; }
[data-testid="stTab"] {
    padding: 0.45rem 0.95rem !important; border-radius: 999px; height: auto;
    border: 1px solid rgba(128, 128, 128, 0.25);
}
[data-testid="stTab"][aria-selected="true"] { background: rgba(20, 184, 166, 0.14); border-color: rgba(20, 184, 166, 0.6); }
[data-testid="stTabs"] .react-aria-SelectionIndicator { display: none; }

/* ---------- Barra lateral ---------- */
.marca { display: flex; align-items: center; gap: 0.6rem; margin: -0.5rem 0 0.8rem; }
.marca .logo {
    width: 2.4rem; height: 2.4rem; border-radius: 0.75rem; display: grid; place-items: center; font-size: 1.3rem;
    background: linear-gradient(135deg, #0f766e, #22c55e); box-shadow: 0 6px 14px -6px rgba(15, 118, 110, 0.8);
}
.marca b { font-size: 1.05rem; display: block; }
.marca span { font-size: 0.78rem; opacity: 0.7; }
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] { justify-content: flex-start; }
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] > div { justify-content: flex-start !important; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { margin-top: -0.6rem; padding-left: 0.4rem; }
/* Ajustes abajo del todo: la barra lateral ocupa toda la altura y lo de arriba empuja hacia abajo
   (con muchos cuadres, simplemente quedan al final de la lista) */
[data-testid="stSidebarContent"] { display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] { flex: 1; display: flex; flex-direction: column; padding-bottom: 1.2rem; }
[data-testid="stSidebarUserContent"] > div { flex: 1; display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] { flex: 1; }
[data-testid="stLayoutWrapper"]:has(> .st-key-ajustes) {
    margin-top: auto; padding-top: 0.8rem; border-top: 1px solid rgba(128, 128, 128, 0.2);
}

/* Panel de «Avanzado»: más ancho que el botón, para que se lean los nombres de los modelos */
[data-testid="stPopoverBody"] { min-width: 340px; }

/* ---------- Desplegables ---------- */
[data-testid="stExpander"] details { border-radius: 0.9rem; }
[data-testid="stExpander"] summary p { font-weight: 600; }
</style>
"""


def aplicar():
    """Añade los estilos a la página. Un st.html con solo <style> no ocupa sitio."""
    st.html(CSS)


def marca():
    """Logo y nombre de la app en la barra lateral."""
    st.html('<div class="marca"><div class="logo">🧾</div>'
            '<div><b>Cuadra tus gastos</b><span>Tickets y banco, en un minuto</span></div></div>')


def titulo_tarjeta(icono, titulo, detalle):
    """Cabecera de una tarjeta: icono, título en negrita y una línea de ayuda."""
    st.html(f'<div class="titulo-tarjeta"><div class="icono">{icono}</div>'
            f'<div><b>{escape(titulo)}</b><span>{escape(detalle)}</span></div></div>')


# ---------- Lista de movimientos (tarjetas que se despliegan) ----------
# Un componente propio (st.components.v2), como los de almacen.py: HTML y JavaScript en la página.
# Cada movimiento es una tarjeta; al pulsarla se despliegan sus comprobantes. Al pulsar un comprobante,
# Python abre el visor; el botón de descarga baja el archivo directamente del navegador (IndexedDB).
# Todos los textos se ponen con textContent: nada de lo leído por la IA se interpreta como HTML.

JS_LISTA = almacen.JS_BD + """
const ICONO_PDF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 15h6M9 18h4"/></svg>';
const ICONO_FOTO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5L5 20"/></svg>';
const ICONO_DESCARGA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14"/></svg>';
const ICONO_DOC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>';
const ICONO_FLECHA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';

function nodo(etiqueta, clase, texto) {
    const n = document.createElement(etiqueta);
    if (clase) n.className = clase;
    if (texto !== undefined) n.textContent = texto;
    return n;
}

// Baja el archivo guardado en el navegador; si no está, se pide a Python que abra el visor
async function descargar(comprobante, setTriggerValue) {
    try {
        if (!comprobante.huella) throw new Error("sin huella");
        const bd = await abrir();
        const archivo = await pedir(bd.transaction("archivos").objectStore("archivos").get(comprobante.huella));
        bd.close();
        if (!archivo) throw new Error("no guardado");
        const url = URL.createObjectURL(archivo.blob);
        const enlace = document.createElement("a");
        enlace.href = url;
        enlace.download = comprobante.archivo;
        enlace.click();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) {
        setTriggerValue("abrir", comprobante.archivo);
    }
}

function filaComprobante(c, setTriggerValue) {
    const fila = nodo("div", "comprobante");
    const ver = nodo("button", "ver");
    ver.type = "button";
    ver.title = "Ver el comprobante";
    ver.onclick = () => setTriggerValue("abrir", c.archivo);
    const icono = nodo("span", "icono-archivo" + (c.es_pdf ? " pdf" : " foto"));
    icono.innerHTML = c.es_pdf ? ICONO_PDF : ICONO_FOTO;
    const textos = nodo("span", "textos");
    textos.append(nodo("span", "nombre", c.archivo), nodo("span", "detalle", c.detalle));
    ver.append(icono, textos, nodo("span", "importe-archivo", c.importe));
    const bajar = nodo("button", "descargar");
    bajar.type = "button";
    bajar.title = "Descargar";
    bajar.setAttribute("aria-label", "Descargar " + c.archivo);
    bajar.innerHTML = ICONO_DESCARGA;
    bajar.onclick = () => descargar(c, setTriggerValue);
    fila.append(ver, bajar);
    return fila;
}

export default function ({ data, parentElement, setTriggerValue }) {
    // Qué tarjetas están abiertas: se recuerda entre ejecuciones de Streamlit
    const abiertas = (window.cuadraTarjetasAbiertas ??= new Set());
    parentElement.querySelectorAll(".lista").forEach((n) => n.remove());
    const lista = nodo("div", "lista");
    if (!data.movimientos.length) lista.append(nodo("p", "vacia", data.vacia));

    for (const m of data.movimientos) {
        const tarjeta = nodo("div", "tarjeta" + (abiertas.has(m.id) ? " abierta" : ""));
        const cabecera = nodo("button", "cabecera");
        cabecera.type = "button";
        cabecera.setAttribute("aria-expanded", abiertas.has(m.id));

        const icono = nodo("span", "icono", m.icono);
        icono.style.setProperty("--tono", m.tono);
        const fecha = nodo("span", "fecha");
        fecha.append(nodo("span", "dia", m.fecha), nodo("span", "semana", m.semana));
        const texto = nodo("span", "texto");
        texto.append(nodo("span", "titulo", m.titulo), nodo("span", "subtitulo", m.subtitulo));
        const chips = nodo("span", "chips");
        for (const chip of m.chips) {
            const etiqueta = nodo("span", "chip " + chip.tipo, chip.texto);
            if (chip.tipo === "ok") etiqueta.insertAdjacentHTML("afterbegin", ICONO_DOC);  // como un documento
            chips.append(etiqueta);
        }
        texto.append(chips);
        const importe = nodo("span", "importe" + (m.ingreso ? " ingreso" : ""), m.importe);
        const flecha = nodo("span", "flecha");
        flecha.innerHTML = ICONO_FLECHA;
        cabecera.append(icono, fecha, texto, importe, flecha);

        const cuerpo = nodo("div", "cuerpo");
        const caja = nodo("div", "caja");
        if (m.comprobantes.length) {
            caja.append(nodo("div", "titulo-caja", `Comprobantes (${m.comprobantes.length})`));
            for (const c of m.comprobantes) caja.append(filaComprobante(c, setTriggerValue));
        } else {
            caja.append(nodo("p", "sin", m.sin_comprobantes));
        }
        if (m.nota) caja.append(nodo("p", "nota", m.nota));
        cuerpo.append(caja);

        cabecera.onclick = () => {
            const abierta = tarjeta.classList.toggle("abierta");
            cabecera.setAttribute("aria-expanded", abierta);
            if (abierta) abiertas.add(m.id); else abiertas.delete(m.id);
        };
        tarjeta.append(cabecera, cuerpo);
        lista.append(tarjeta);
    }
    parentElement.append(lista);
    return () => lista.remove();
}
"""

CSS_LISTA = """
.lista { display: flex; flex-direction: column; gap: 0.6rem; font-family: var(--st-font, inherit); color: var(--st-text-color); }
.tarjeta {
    border: 1px solid var(--st-border-color, rgba(128, 128, 128, 0.25)); border-radius: 1rem;
    background: var(--st-background-color); overflow: hidden; transition: border-color 0.15s ease;
}
.tarjeta:hover, .tarjeta.abierta { border-color: rgba(20, 184, 166, 0.55); }
button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; text-align: left; }
.cabecera {
    width: 100%; display: grid; grid-template-columns: auto 7.5rem 1fr auto auto; align-items: center;
    gap: 1rem; padding: 0.85rem 1.1rem;
}
.tarjeta.abierta .cabecera { background: rgba(20, 184, 166, 0.07); }
.icono {
    width: 2.9rem; height: 2.9rem; border-radius: 50%; display: grid; place-items: center; font-size: 1.3rem;
    background: color-mix(in srgb, var(--tono) 22%, transparent);
}
.fecha { display: flex; flex-direction: column; padding-right: 1rem; border-right: 1px solid rgba(128, 128, 128, 0.22); }
.dia { font-size: 0.98rem; }
.semana { font-size: 0.8rem; opacity: 0.6; }
.texto { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
.titulo { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.subtitulo { font-size: 0.88rem; opacity: 0.7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.3rem; }
.chip svg { width: 0.9rem; height: 0.9rem; vertical-align: -0.15rem; margin-right: 0.3rem; }
.chip { font-size: 0.78rem; font-weight: 600; padding: 0.18rem 0.6rem; border-radius: 999px; background: rgba(128, 128, 128, 0.16); }
.chip.ok { background: rgba(59, 130, 246, 0.14); color: #3b82f6; }
.chip.aviso { background: rgba(234, 179, 8, 0.18); color: #ca8a04; }
.chip.falta { background: rgba(239, 68, 68, 0.14); color: #ef4444; }
.chip.info { background: rgba(20, 184, 166, 0.14); color: #0d9488; }
.importe { font-size: 1.15rem; font-weight: 700; white-space: nowrap; font-variant-numeric: tabular-nums; }
.importe.ingreso { color: #16a34a; }
.flecha { width: 1.3rem; height: 1.3rem; opacity: 0.6; transition: transform 0.2s ease; }
.tarjeta.abierta .flecha { transform: rotate(180deg); }
.cuerpo { display: none; padding: 0 1rem 1rem; }
.tarjeta.abierta .cuerpo { display: block; }
.caja {
    border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 0.8rem; padding: 0.8rem; margin-top: 0.8rem;
    background: var(--st-secondary-background-color);
}
.titulo-caja { font-weight: 700; margin: 0.1rem 0.2rem 0.6rem; }
.comprobante {
    display: flex; align-items: center; gap: 0.4rem; border: 1px solid rgba(128, 128, 128, 0.2);
    border-radius: 0.7rem; margin-top: 0.45rem; padding-right: 0.5rem; background: var(--st-background-color);
}
.ver { flex: 1; display: flex; align-items: center; gap: 0.8rem; padding: 0.6rem 0.8rem; min-width: 0; border-radius: 0.7rem; }
.ver:hover { background: rgba(20, 184, 166, 0.07); }
.icono-archivo { flex: none; width: 2.3rem; height: 2.3rem; border-radius: 50%; display: grid; place-items: center; }
.icono-archivo svg, .descargar svg, .flecha svg { width: 1.2rem; height: 1.2rem; }
.icono-archivo.pdf { background: rgba(239, 68, 68, 0.12); color: #ef4444; }
.icono-archivo.foto { background: rgba(59, 130, 246, 0.12); color: #3b82f6; }
.textos { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.nombre { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.detalle { font-size: 0.82rem; opacity: 0.65; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.importe-archivo { font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
.descargar { width: 2.2rem; height: 2.2rem; border-radius: 0.5rem; display: grid; place-items: center; opacity: 0.75; }
.descargar:hover { opacity: 1; background: rgba(128, 128, 128, 0.15); }
.sin, .nota, .vacia { margin: 0.2rem; font-size: 0.9rem; opacity: 0.75; }
.nota { margin-top: 0.6rem; }
@media (max-width: 640px) {
    .cabecera { grid-template-columns: auto 1fr auto; gap: 0.7rem; padding: 0.75rem; }
    .fecha, .flecha { display: none; }
    .importe { font-size: 1rem; }
}
"""

_lista = st.components.v2.component("lista_movimientos", js=JS_LISTA, css=CSS_LISTA)


def lista_movimientos(movimientos, al_abrir, key, vacia="No hay movimientos."):
    """Dibuja los movimientos como tarjetas. `al_abrir(nombre_de_archivo)` se llama al pulsar un comprobante.

    Cada movimiento es un dict con: id, icono, tono, fecha, semana, titulo, subtitulo, chips [{texto, tipo}],
    importe (texto), ingreso (bool), comprobantes [{archivo, detalle, importe, huella, es_pdf}],
    sin_comprobantes (texto) y nota (texto o "").
    """
    def avisar():
        nombre = st.session_state[key].abrir
        if nombre:
            al_abrir(nombre)

    _lista(data={"movimientos": movimientos, "vacia": vacia}, key=key, on_abrir_change=avisar)
