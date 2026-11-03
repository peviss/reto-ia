"""Guardar el cuadre en la Google Drive del usuario, con OAuth en el navegador (F3).

Es un componente (`st.components.v2`) con un poco de JavaScript que usa Google Identity Services:
1. Al pulsar el botón, Google abre una ventana para que el usuario entre con SU cuenta y dé permiso.
   El permiso es `drive.file`: la app solo ve los archivos que crea ella, no el resto de su Drive.
2. Con el token de acceso que devuelve Google, el navegador sube el Excel a la carpeta «Cuadra tus gastos»
   de su Drive (la crea la primera vez), convertido en hoja de cálculo de Google.

El token se queda en el navegador (dura una hora) y nunca llega al servidor de la app. Solo hace falta
el `client_id` de un cliente OAuth «Aplicación web» de Google Cloud en los secretos (`[google_drive]`):
no es secreto, pero así se cambia sin tocar el código. No hay `client_secret`.
"""

import base64
import logging

import streamlit as st

log = logging.getLogger("cuadra")

JS = """
const ALCANCE = "https://www.googleapis.com/auth/drive.file";
const CARPETA = "Cuadra tus gastos";
const API = "https://www.googleapis.com/drive/v3/files";
const SUBIDA = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink";
const MIME_HOJA = "application/vnd.google-apps.spreadsheet";

// Fuera de la función: se mantiene mientras la página esté abierta, aunque Streamlit vuelva a dibujar
let token = null;  // { valor, vence }
let cargando = null;

function cargarGoogle() {
    if (!cargando) {
        cargando = new Promise((ok, mal) => {
            if (window.google?.accounts?.oauth2) return ok();
            const script = document.createElement("script");
            script.src = "https://accounts.google.com/gsi/client";
            script.async = true;
            script.onload = () => ok();
            script.onerror = () => { cargando = null; mal(new Error("sin conexión con Google")); };
            document.head.appendChild(script);
        });
    }
    return cargando;
}

function pedirPermiso(clientId) {
    // Se llama directamente desde el clic: si no, el navegador bloquea la ventana de Google
    return new Promise((ok, mal) => {
        google.accounts.oauth2.initTokenClient({
            client_id: clientId, scope: ALCANCE,
            callback: (r) => r.error ? mal(new Error(r.error)) : ok(r),
            error_callback: (e) => mal(new Error(e.type || "cancelado")),
        }).requestAccessToken();
    });
}

async function llamar(url, opciones) {
    const r = await fetch(url, { ...opciones, headers: { ...opciones.headers, Authorization: `Bearer ${token.valor}` } });
    if (r.status === 401) { token = null; throw new Error("caducado"); }
    if (!r.ok) throw new Error(`error ${r.status}`);
    return r.json();
}

async function carpeta() {
    // Con drive.file solo se encuentran las carpetas que ha creado esta app
    const q = encodeURIComponent(`name='${CARPETA}' and mimeType='application/vnd.google-apps.folder' and trashed=false`);
    const hay = await llamar(`${API}?q=${q}&fields=files(id)`, { headers: {} });
    if (hay.files.length) return hay.files[0].id;
    const nueva = await llamar(`${API}?fields=id`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: CARPETA, mimeType: "application/vnd.google-apps.folder" }),
    });
    return nueva.id;
}

async function subir(data) {
    // Subida «multipart»: en una sola petición, primero los datos del archivo y luego el archivo
    const separador = "cuadra-" + crypto.randomUUID();
    const datos = { name: data.nombre, mimeType: MIME_HOJA, parents: [await carpeta()] };
    const excel = Uint8Array.from(atob(data.excel), (c) => c.charCodeAt(0));
    const cuerpo = new Blob([
        `--${separador}\\r\\nContent-Type: application/json; charset=UTF-8\\r\\n\\r\\n${JSON.stringify(datos)}\\r\\n`,
        `--${separador}\\r\\nContent-Type: ${data.mime}\\r\\n\\r\\n`, excel, `\\r\\n--${separador}--\\r\\n`,
    ]);
    return llamar(SUBIDA, { method: "POST", headers: { "Content-Type": `multipart/related; boundary=${separador}` }, body: cuerpo });
}

function mensaje(e) {
    const texto = String(e?.message || e);
    if (texto.includes("popup_closed") || texto.includes("cancelado") || texto.includes("access_denied"))
        return "No se ha dado permiso a Google Drive. Pulse el botón otra vez si quiere guardarlo.";
    if (texto.includes("popup_failed")) return "El navegador ha bloqueado la ventana de Google. Permita las ventanas emergentes de esta página.";
    if (texto.includes("caducado")) return "La conexión con Google Drive ha caducado. Pulse el botón otra vez.";
    if (texto.includes("sin conexión") || texto.includes("Failed to fetch")) return "No hay conexión con Google. Pruebe de nuevo en unos minutos.";
    if (texto.includes("error 403")) return "Google Drive no deja guardar el archivo (permiso denegado o sin espacio).";
    return "No se ha podido guardar en Google Drive. Pruebe de nuevo en unos minutos.";
}

export default function ({ data, parentElement, setTriggerValue }) {
    parentElement.querySelectorAll(".drive").forEach((n) => n.remove());  // si se vuelve a llamar
    const caja = document.createElement("div");
    caja.className = "drive";
    const boton = document.createElement("button");
    const estado = document.createElement("p");
    const salir = document.createElement("a");
    salir.href = "#";
    salir.textContent = "Desconectar Google Drive";
    caja.append(boton, estado, salir);
    parentElement.appendChild(caja);

    const conectado = () => token && Date.now() < token.vence;
    const pintar = () => {
        boton.textContent = conectado() ? "📁 Guardar en mi Google Drive" : "🔐 Conectar con Google Drive y guardar";
        salir.hidden = !conectado();
    };
    const avisar = (texto, tipo) => { estado.textContent = texto; estado.className = tipo || ""; };
    pintar();
    cargarGoogle().catch(() => avisar(mensaje("sin conexión"), "error"));  // se carga ya, antes del clic

    boton.onclick = async () => {
        boton.disabled = true;
        try {
            if (!conectado()) {
                if (!window.google?.accounts?.oauth2) throw new Error("sin conexión");
                const r = await pedirPermiso(data.client_id);
                token = { valor: r.access_token, vence: Date.now() + (r.expires_in - 60) * 1000 };
                pintar();
            }
            avisar("Guardando en su Google Drive…");
            const archivo = await subir(data);
            estado.textContent = "✅ Guardado en su Google Drive, en la carpeta «Cuadra tus gastos». ";
            estado.className = "ok";
            const abrir = document.createElement("a");
            abrir.href = archivo.webViewLink;
            abrir.target = "_blank";
            abrir.rel = "noopener";
            abrir.textContent = "Abrirlo";
            estado.appendChild(abrir);
            setTriggerValue("guardado", data.nombre);
        } catch (e) {
            avisar(mensaje(e), "error");
            setTriggerValue("fallo", String(e?.message || e));
        } finally {
            boton.disabled = false;
            pintar();
        }
    };
    salir.onclick = (evento) => {
        evento.preventDefault();
        if (token) google.accounts.oauth2.revoke(token.valor, () => {});
        token = null;
        avisar("Se ha desconectado Google Drive.");
        pintar();
    };
    return () => caja.remove();
}
"""

CSS = """
.drive { font-family: var(--st-font); }
button {
    width: 100%; padding: 0.5rem 0.75rem; border-radius: var(--st-base-radius, 0.5rem); cursor: pointer;
    border: 0; background: var(--st-primary-color); color: #fff; font: inherit; font-weight: 600;
}
button:disabled { opacity: 0.6; cursor: wait; }
p { color: var(--st-text-color); margin: 0.5rem 0; font-size: 0.9rem; }
p.ok { color: var(--st-green-color, #16a34a); }
p.error { color: var(--st-red-color, #dc2626); }
a { color: var(--st-primary-color); font-size: 0.85rem; }
"""

_componente = st.components.v2.component("google_drive", js=JS, css=CSS)


def client_id():
    """El client_id de Google de los secretos ([google_drive]), o None: sin él no sale Google Drive."""
    try:
        return st.secrets["google_drive"]["client_id"] or None
    except Exception:  # sin secrets.toml o sin esa sección
        return None


def boton_guardar(id_cliente, nombre, excel, mime, key):
    """Dibuja el botón que conecta con la Google Drive del usuario y guarda en ella el Excel."""
    def al_guardar():
        log.info("Cuadre «%s» guardado en la Google Drive del usuario", st.session_state[key].guardado)

    def al_fallar():
        log.warning("No se ha podido guardar en Google Drive: %s", st.session_state[key].fallo)

    _componente(
        key=key,
        data={"client_id": id_cliente, "nombre": nombre, "mime": mime, "excel": base64.b64encode(excel).decode()},
        on_guardado_change=al_guardar,
        on_fallo_change=al_fallar,
    )
