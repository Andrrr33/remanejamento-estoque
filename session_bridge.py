"""Cookie HttpOnly para conservar a sessão após F5 na execução local."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import threading
from urllib.parse import urlparse

import streamlit as st

from auth import tocar_sessao, validar_sessao

PORTA = int(os.getenv("APP_SESSION_PORT", "8774"))
PORTA_STREAMLIT = int(st.get_option("server.port") or 8504)
_endereco_configurado = os.getenv("APP_SESSION_BIND_ADDRESS", "127.0.0.1")
ENDERECO = (
    socket.gethostbyname(socket.gethostname())
    if _endereco_configurado == "lan"
    else _endereco_configurado
)
CERTIFICADO = st.get_option("server.sslCertFile")
CHAVE = st.get_option("server.sslKeyFile")
COOKIE = "portfolio_remanejamento_sessao"
_SERVIDOR: ThreadingHTTPServer | None = None
_TRAVA = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def _origem_permitida(self) -> str | None:
        origem = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        try:
            parsed = urlparse(origem)
            destino = urlparse(f"//{host}")
            if (
                parsed.scheme == ("https" if CERTIFICADO else "http")
                and parsed.hostname
                and parsed.hostname == destino.hostname
                and parsed.port == PORTA_STREAMLIT
                and destino.port == PORTA
                and not parsed.username
                and not parsed.password
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
            ):
                return origem
        except ValueError:
            pass
        return None

    def _headers(self, origem: str, status: int = 200, cookie: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json")
        if cookie is not None:
            seguro = "; Secure" if origem.startswith("https:") else ""
            self.send_header(
                "Set-Cookie",
                f"{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path=/; "
                f"Max-Age={300 if cookie else 0}{seguro}",
            )
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"rc-bridge-v1")

    def do_OPTIONS(self) -> None:
        origem = self._origem_permitida()
        if not origem:
            self.send_error(403)
            return
        self._headers(origem, 204)

    def do_POST(self) -> None:
        origem = self._origem_permitida()
        if not origem or self.path not in ("/session", "/touch", "/clear"):
            self.send_error(403)
            return
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if tamanho < 0 or tamanho > 512:
            self.send_error(413)
            return
        self.connection.settimeout(5)
        corpo = self.rfile.read(tamanho) if tamanho else b""
        if self.path == "/clear":
            self._headers(origem, cookie="")
            self.wfile.write(b'{"ok":true}')
            return
        if self.path == "/session":
            try:
                token = json.loads(corpo).get("token")
            except (ValueError, AttributeError):
                token = None
            valido = bool(validar_sessao(token))
        else:
            token = None
            for item in self.headers.get("Cookie", "").split(";"):
                chave, _, valor = item.strip().partition("=")
                if chave == COOKIE:
                    token = valor
                    break
            valido = tocar_sessao(token)
        if valido:
            self._headers(origem, cookie=token)
            self.wfile.write(b'{"ok":true}')
        else:
            self._headers(origem, 401, cookie="")
            self.wfile.write(b'{"ok":false}')


def ensure_bridge() -> None:
    global _SERVIDOR
    with _TRAVA:
        if _SERVIDOR is None:
            endereco = ipaddress.ip_address(ENDERECO)
            if not endereco.is_loopback and not (CERTIFICADO and CHAVE):
                raise RuntimeError(
                    "A sessão pela rede exige HTTPS no Streamlit e no serviço de sessão. "
                    "Configure server.sslCertFile e server.sslKeyFile antes de usar APP_SESSION_BIND_ADDRESS."
                )
            try:
                servidor = ThreadingHTTPServer((ENDERECO, PORTA), _Handler)
                if CERTIFICADO and CHAVE:
                    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
                    contexto.load_cert_chain(
                        certfile=str(Path(CERTIFICADO).expanduser()),
                        keyfile=str(Path(CHAVE).expanduser()),
                    )
                    servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
                _SERVIDOR = servidor
            except (OSError, ssl.SSLError):
                return
            threading.Thread(
                target=_SERVIDOR.serve_forever,
                name="rc-cookie-bridge",
                daemon=True,
            ).start()


def _browser_renderer():
    return st.components.v2.component(
        "rc_test_session_browser_v1",
        html="<span aria-hidden='true'></span>",
        js="""
export default function({ data, parentElement, setTriggerValue }) {
  const endpoint = `${window.location.protocol}//${window.location.hostname}:${data.port}`;
  let disposed = false;
  const firstMount = !window.__rcSessionActivity;
  const activity = window.__rcSessionActivity || (window.__rcSessionActivity = {
    lastActivity: Date.now(), lastTouch: 0
  });
  if (data.action === 'set' || !data.loggedIn) {
    activity.lastActivity = Date.now();
    activity.lastTouch = 0;
  }
  const expire = () => {
    if (!disposed) setTriggerValue('expired', true);
  };
  const post = (path, body) => fetch(endpoint + path, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {})
  });
  if (data.action === 'set' && data.token) {
    post('/session', { token: data.token })
      .then(response => { if (!disposed) setTriggerValue('cookie_ready', response.ok); })
      .catch(() => { if (!disposed) setTriggerValue('cookie_ready', false); });
  } else if (data.action === 'clear') {
    post('/clear').catch(() => {});
  } else if (data.action === 'watch' && firstMount && data.loggedIn) {
    post('/touch').then(response => {
      if (!response.ok) expire();
    }).catch(() => {});
  }
  const onActivity = () => {
    if (!data.loggedIn) return;
    const now = Date.now();
    if (now - activity.lastActivity >= 300000) {
      expire();
      return;
    }
    activity.lastActivity = now;
    if (now - activity.lastTouch < 15000) return;
    activity.lastTouch = now;
    post('/touch').then(response => {
      if (!response.ok) expire();
    }).catch(() => {});
  };
  for (const eventName of ['pointerdown', 'keydown', 'input', 'wheel']) {
    document.addEventListener(eventName, onActivity, { capture: true, passive: true });
  }
  const idleTimer = window.setInterval(() => {
    if (data.loggedIn && Date.now() - activity.lastActivity >= 300000) {
      window.clearInterval(idleTimer);
      expire();
    }
  }, 1000);
  return () => {
    disposed = true;
    window.clearInterval(idleTimer);
    for (const eventName of ['pointerdown', 'keydown', 'input', 'wheel']) {
      document.removeEventListener(eventName, onActivity, true);
    }
  };
}
""",
    )


def acompanhar_navegador(*, action: str = "watch", token: str | None = None, logged_in: bool = False):
    return _browser_renderer()(
        key="rc_browser_session",
        height=0,
        data={"action": action, "token": token, "loggedIn": logged_in, "port": PORTA},
        on_cookie_ready_change=lambda: None,
        on_expired_change=lambda: None,
    )
