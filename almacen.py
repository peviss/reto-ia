"""Guarda en el navegador del usuario (IndexedDB) lo que ha leído la IA, el historial de cuadres
y los archivos de los comprobantes.

- Si se vuelve a subir un archivo ya leído, se usa lo guardado y no se gasta cuota de la IA.
- Cada cuadre (extracto + comprobantes leídos) se guarda para abrirlo, ampliarlo con más
  comprobantes o eliminarlo más tarde desde la barra lateral.
- Las fotos (reducidas) y los PDF de los comprobantes se guardan para verlos al abrir un cuadre.

Todo se queda en el navegador de quien usa la app: no pasa por ningún servidor nuestro.

Streamlit se ejecuta en el servidor y IndexedDB está en el navegador: los une un componente
(`st.components.v2`) con un poco de JavaScript. Python le manda órdenes («guarda esto», «bórralo
todo») en `data`; el JavaScript las hace, avisa con `setTriggerValue("hecha", id)` y, al abrir la
página, devuelve lo guardado con `setStateValue("guardado", …)`. Python trabaja con una copia en
`st.session_state["guardado"]`, así que lo que cambia en esta sesión se ve enseguida.

Los archivos no vuelven nunca a Python (serían muchos MB en cada carga): los muestra el
componente `ver_archivo`, que los lee de IndexedDB directamente en el navegador.
"""

import base64
import hashlib
import logging
import time
import uuid

import streamlit as st

# Súbala si cambian los prompts o los esquemas: lo leído con la versión anterior deja de usarse
VERSION_LECTURA = 1

log = logging.getLogger("cuadra")

# Lo que comparten los dos componentes: abrir la base de datos
JS_BD = """
const BD = "cuadra-tus-gastos";

// Convierte una petición de IndexedDB (con onsuccess/onerror) en una promesa
function pedir(peticion) {
    return new Promise((ok, mal) => {
        peticion.onsuccess = () => ok(peticion.result);
        peticion.onerror = () => mal(peticion.error);
    });
}

function abrir() {
    const peticion = indexedDB.open(BD, 2);
    peticion.onupgradeneeded = () => {
        const bd = peticion.result;
        // lecturas y archivos: clave = huella del archivo; cuadres: clave = id del cuadre
        for (const almacen of ["lecturas", "cuadres", "archivos"]) {
            if (!bd.objectStoreNames.contains(almacen)) bd.createObjectStore(almacen);
        }
    };
    return pedir(peticion);
}
"""

JS = JS_BD + """
// El archivo llega en base64 (dentro del JSON de «data»); se guarda como Blob, que ocupa menos
function aBlob(archivo) {
    const bytes = Uint8Array.from(atob(archivo.b64), (letra) => letra.charCodeAt(0));
    return { nombre: archivo.nombre, mime: archivo.mime, blob: new Blob([bytes], { type: archivo.mime }) };
}

async function ejecutar(bd, orden) {
    const tx = bd.transaction(["lecturas", "cuadres", "archivos"], "readwrite");
    const fin = new Promise((ok, mal) => { tx.oncomplete = ok; tx.onerror = tx.onabort = () => mal(tx.error); });
    const lecturas = tx.objectStore("lecturas"), cuadres = tx.objectStore("cuadres"), archivos = tx.objectStore("archivos");
    if (orden.borrar) {
        lecturas.clear();
        cuadres.clear();
        archivos.clear();
    }
    for (const id of orden.quitar || []) cuadres.delete(id);
    for (const clave of orden.quitar_archivos || []) archivos.delete(clave);
    for (const [clave, datos] of Object.entries(orden.lecturas || {})) lecturas.put(datos, clave);
    for (const [clave, archivo] of Object.entries(orden.archivos || {})) archivos.put(aBlob(archivo), clave);
    // La fecha la pone el navegador, con la hora de quien usa la app
    const fecha = new Date().toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" });
    for (const [id, cuadre] of Object.entries(orden.cuadres || {})) {
        cuadres.put({ ...cuadre, fecha, actualizado: Date.now() }, id);
    }
    await fin;  // todo se guarda junto o no se guarda nada
}

// Devuelve un almacén entero como {clave: valor}
async function todo(tx, almacen) {
    const [claves, valores] = await Promise.all([
        pedir(tx.objectStore(almacen).getAllKeys()),
        pedir(tx.objectStore(almacen).getAll()),
    ]);
    return Object.fromEntries(claves.map((clave, i) => [clave, valores[i]]));
}

// Los archivos no se mandan: se quedan en el navegador
async function leerTodo(bd) {
    const tx = bd.transaction(["lecturas", "cuadres"]);
    const [lecturas, cuadres] = await Promise.all([todo(tx, "lecturas"), todo(tx, "cuadres")]);
    return { lecturas, cuadres };
}

export default function ({ data, setStateValue, setTriggerValue }) {
    // Streamlit vuelve a llamar a esta función en cada ejecución: cada orden se hace una sola vez
    const hechas = (window.cuadraOrdenesHechas ??= new Set());
    (async () => {
        try {
            const bd = await abrir();
            const orden = data?.orden;
            if (orden && !hechas.has(orden.id)) {
                hechas.add(orden.id);
                try {
                    await ejecutar(bd, orden);
                } catch (e) {  // p. ej. no queda espacio
                    console.warn("[cuadra] No se ha podido guardar:", e);
                    setTriggerValue("fallo", String(e));
                }
            }
            if (orden) setTriggerValue("hecha", orden.id);  // Python deja de mandarla
            if (data?.cargar) setStateValue("guardado", await leerTodo(bd));
            bd.close();
        } catch (e) {  // p. ej. navegación privada o almacenamiento bloqueado
            console.warn("[cuadra] No se puede usar IndexedDB:", e);
            if (data?.cargar) setStateValue("guardado", { error: String(e) });
        }
    })();
}
"""

JS_VISOR = JS_BD + """
export default function ({ data, parentElement }) {
    parentElement.querySelectorAll(".visor").forEach((n) => n.remove());  // si se vuelve a llamar
    const caja = document.createElement("div");
    caja.className = "visor";
    parentElement.appendChild(caja);
    const avisar = (texto) => { caja.innerHTML = ""; const p = document.createElement("p"); p.textContent = texto; caja.appendChild(p); };
    let url = null;
    (async () => {
        try {
            const bd = await abrir();
            const archivo = await pedir(bd.transaction("archivos").objectStore("archivos").get(data.huella));
            bd.close();
            if (!archivo) {
                avisar("Este comprobante se guardó sin su archivo. Vuelva a subirlo y pulse «Añadir al cuadre».");
                return;
            }
            url = URL.createObjectURL(archivo.blob);
            if (archivo.mime === "application/pdf") {
                const marco = document.createElement("iframe");
                marco.src = url;
                caja.appendChild(marco);
            } else {
                const imagen = document.createElement("img");
                imagen.src = url;
                imagen.alt = data.nombre;
                imagen.onerror = () => avisar("Esta foto no se puede mostrar aquí, pero puede descargarla.");
                caja.appendChild(imagen);
            }
            const descargar = document.createElement("a");
            descargar.href = url;
            descargar.download = data.nombre;
            descargar.textContent = "⬇️ Descargar el archivo";
            caja.appendChild(descargar);
        } catch (e) {
            avisar("No se ha podido abrir el archivo guardado en este navegador.");
        }
    })();
    return () => { if (url) URL.revokeObjectURL(url); caja.remove(); };
}
"""

CSS_VISOR = """
img { max-width: 100%; display: block; margin-bottom: 0.75rem; }
iframe { width: 100%; height: 600px; border: 0; margin-bottom: 0.75rem; }
a { color: var(--st-primary-color); }
p { color: var(--st-text-color); }
"""

_componente = st.components.v2.component("almacen_navegador", js=JS)
_visor = st.components.v2.component("visor_comprobante", js=JS_VISOR, css=CSS_VISOR)


def huella(tipo, archivo):
    """Identifica un archivo por su contenido: el mismo archivo da la misma huella aunque cambie de nombre."""
    return f"{tipo}-v{VERSION_LECTURA}-" + hashlib.sha256(archivo["datos"]).hexdigest()


def _guardado():
    """La copia de esta sesión de lo guardado en el navegador."""
    if "guardado" not in st.session_state:
        st.session_state["guardado"] = {"lecturas": {}, "cuadres": {}}
    return st.session_state["guardado"]


def cargado():
    """True cuando ya ha llegado lo guardado en el navegador (o se sabe que no se puede usar)."""
    return st.session_state.get("guardado_cargado", False)


def lectura(clave):
    return _guardado()["lecturas"].get(clave)


def cuadres():
    """Los cuadres guardados, del más reciente al más antiguo."""
    return sorted(_guardado()["cuadres"].values(), key=lambda c: c.get("actualizado", 0), reverse=True)


def cuadre(id_cuadre):
    return _guardado()["cuadres"].get(id_cuadre) if id_cuadre else None


def nuevo_id():
    return uuid.uuid4().hex


# ---------- Órdenes para el navegador ----------

def _orden_vacia():
    return {"lecturas": {}, "cuadres": {}, "archivos": {}, "quitar": [], "quitar_archivos": [], "borrar": False}


def _juntar(antes, despues):
    """Una sola orden que hace lo mismo que `antes` y, a continuación, `despues`."""
    if despues["borrar"]:  # lo de antes se borra igualmente
        return despues
    junta = _orden_vacia()
    junta["borrar"] = antes["borrar"]
    junta["lecturas"] = {**antes["lecturas"], **despues["lecturas"]}
    junta["cuadres"] = {i: c for i, c in antes["cuadres"].items() if i not in despues["quitar"]}
    junta["cuadres"].update(despues["cuadres"])
    junta["archivos"] = {h: a for h, a in antes["archivos"].items() if h not in despues["quitar_archivos"]}
    junta["archivos"].update(despues["archivos"])
    # El navegador quita antes de guardar: así lo que se vuelve a guardar después no se pierde
    junta["quitar"] = [i for i in antes["quitar"] + despues["quitar"] if i not in despues["cuadres"]]
    junta["quitar_archivos"] = [h for h in antes["quitar_archivos"] + despues["quitar_archivos"]
                                if h not in despues["archivos"]]
    return junta


def _ordenar(**cambios):
    """Añade cambios a la orden que se mandará al navegador al final de esta ejecución."""
    nueva = {**_orden_vacia(), **cambios}
    st.session_state["orden_nueva"] = _juntar(st.session_state.get("orden_nueva") or _orden_vacia(), nueva)


# ---------- Lo que usa app.py ----------

def guardar_lecturas(lecturas):
    """lecturas: {huella: lo que ha leído la IA de ese archivo}."""
    if lecturas:
        _ordenar(lecturas=lecturas)
        _guardado()["lecturas"].update(lecturas)


def guardar_archivos(archivos):
    """archivos: {huella: archivo (dict con nombre, datos y mime)}. Van en base64 dentro del JSON."""
    if archivos:
        _ordenar(archivos={
            clave: {"nombre": a["nombre"], "mime": a["mime"], "b64": base64.b64encode(a["datos"]).decode()}
            for clave, a in archivos.items()
        })


def _en_uso(excepto):
    """Huellas de los archivos que usan los cuadres guardados, salvo el cuadre `excepto`."""
    return {h for c in _guardado()["cuadres"].values() if c["id"] != excepto for h in c.get("huellas", {}).values()}


def guardar_cuadre(datos):
    """Crea o actualiza un cuadre. `datos` lleva su «id» y, en «huellas», {nombre de archivo: huella}."""
    anterior = cuadre(datos["id"]) or {}
    # Archivos que el cuadre ya no usa (p. ej. un ticket sustituido) y ningún otro cuadre necesita
    sobran = set(anterior.get("huellas", {}).values()) - set(datos.get("huellas", {}).values()) - _en_uso(datos["id"])
    # Hasta que el navegador le ponga su fecha, se ordena con la hora de aquí
    datos = {**datos, "actualizado": time.time() * 1000}
    _ordenar(cuadres={datos["id"]: datos}, quitar_archivos=sorted(sobran))
    _guardado()["cuadres"][datos["id"]] = datos


def eliminar_cuadre(id_cuadre):
    sobran = set((cuadre(id_cuadre) or {}).get("huellas", {}).values()) - _en_uso(id_cuadre)
    _ordenar(quitar=[id_cuadre], quitar_archivos=sorted(sobran))
    _guardado()["cuadres"].pop(id_cuadre, None)


def borrar_todo():
    _ordenar(borrar=True)
    st.session_state["guardado"] = {"lecturas": {}, "cuadres": {}}


def ver_archivo(clave, nombre):
    """Muestra el archivo guardado con esa huella (foto o PDF) con un enlace para descargarlo."""
    _visor(data={"huella": clave, "nombre": nombre}, key=f"visor_{clave}")


# ---------- Conexión con el navegador ----------

def _al_cargar():
    """El navegador ha mandado lo que tenía guardado: se junta con lo hecho en esta sesión."""
    recibido = st.session_state["almacen"].guardado or {}
    if "error" in recibido:
        log.warning("No se puede guardar en el navegador: %s", recibido["error"])
    local = _guardado()
    cuadres_recibidos = {
        # Las versiones anteriores guardaban un solo cuadre con la clave «ultimo», sin id ni nombre
        id_cuadre: {"id": id_cuadre, "nombre": c.get("extracto", "Cuadre"), **c}
        for id_cuadre, c in (recibido.get("cuadres") or {}).items()
    }
    st.session_state["guardado"] = {
        "lecturas": {**(recibido.get("lecturas") or {}), **local["lecturas"]},
        "cuadres": {**cuadres_recibidos, **local["cuadres"]},
    }
    st.session_state["guardado_cargado"] = True
    log.info("Guardado en el navegador: %d lecturas y %d cuadres",
             len(st.session_state["guardado"]["lecturas"]), len(st.session_state["guardado"]["cuadres"]))


def _al_hacerse():
    """El navegador ha hecho la orden: ya no hay que mandarla más (con archivos, pesa varios MB)."""
    enviada = st.session_state.get("orden_enviada")
    if enviada and st.session_state["almacen"].hecha == enviada["id"]:
        del st.session_state["orden_enviada"]


def _al_fallar():
    log.warning("El navegador no ha podido guardar: %s", st.session_state["almacen"].fallo)
    st.toast("⚠️ No se ha podido guardar en este navegador (puede que no quede espacio).")


def sincronizar():
    """Monta el componente (no se ve). Hay que llamarlo una vez por ejecución, al final de app.py,
    para que mande las órdenes que se hayan hecho durante la ejecución."""
    if "orden_nueva" in st.session_state:
        nueva = st.session_state.pop("orden_nueva")
        pendiente = st.session_state.get("orden_enviada")
        if pendiente:  # el navegador aún no la ha confirmado: se manda junto con la nueva
            nueva = _juntar({k: v for k, v in pendiente.items() if k != "id"}, nueva)
        # El id evita que el navegador repita la orden si le llega otra vez
        st.session_state["orden_enviada"] = {**nueva, "id": nuevo_id()}
    _componente(
        key="almacen",
        data={"cargar": not cargado(), "orden": st.session_state.get("orden_enviada")},
        on_guardado_change=_al_cargar,
        on_hecha_change=_al_hacerse,
        on_fallo_change=_al_fallar,
    )
