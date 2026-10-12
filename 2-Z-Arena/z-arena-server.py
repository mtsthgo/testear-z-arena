"""Local Z-Arena bridge: serves the UI and proxies queue actions to its Worker."""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
CONFIG_PATH = ROOT / "z-arena-config.json"
ALLOWED_ACTIONS = {"join", "status", "accept", "start", "decline", "leave", "code", "result", "rating"}
ALLOWED_ORIGINS = {
    "http://127.0.0.1:8765",
    "http://localhost:8765",
    "https://z-arena-web.pages.dev",
}
IPC_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "Z-Arena" / "Z-Arena"
COMMAND_PATH = IPC_DIR / "command.txt"
GAME_STATUS_PATH = IPC_DIR / "status.txt"


def load_worker_url() -> str:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        value = str(config.get("queue_worker_url", "")).strip().rstrip("/")
        if value.startswith("https://"):
            return value
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return ""


def game_is_running() -> bool:
    """Check for the game's process without inspecting or modifying other processes."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Tenkaichi3Decomp.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "tenkaichi3decomp.exe" in result.stdout.casefold()


def call_worker(action: str, payload: dict) -> tuple[int, dict]:
    base = load_worker_url()
    if not base:
        return 503, {"error": "Configura queue_worker_url en z-arena-config.json"}
    request = Request(
        f"{base}/api/queue/{action}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raw_body = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            detail = " ".join(raw_body.split())[:240]
            message = f"Worker respondió HTTP {error.code}"
            if detail:
                message += f": {detail}"
            body = {"error": message}
        return error.code, body
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return 502, {"error": "No se pudo contactar el servicio de cola de Z-Arena"}


def monitor_game_ipc() -> None:
    """Relay lobby codes and match results even when the website tab is minimized or closed."""
    completed: set[str] = set()
    while True:
        try:
            parts = GAME_STATUS_PATH.read_text(encoding="ascii").strip().split("|", 4)
            if len(parts) == 5:
                phase, role, match_id, token, value = parts
                signature = "|".join(parts)
                if signature not in completed and phase == "code" and role == "host":
                    status, _ = call_worker("code", {
                        "token": token, "mode": "Duelo individual", "region": "Sudamérica", "code": value,
                    })
                    if status < 400:
                        completed.add(signature)
                elif signature not in completed and phase == "result":
                    status, _ = call_worker("result", {
                        "token": token, "mode": "Duelo individual", "region": "Sudamérica", "winner_role": value,
                    })
                    if status < 400 or status == 409:
                        completed.add(signature)
        except (OSError, UnicodeError):
            pass
        time.sleep(1)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        print("[Z-Arena] " + format % args, flush=True)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return not origin or origin in ALLOWED_ORIGINS

    def _set_cors_headers(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not urlparse(self.path).path.startswith("/api/"):
            self.send_json(404, {"error": "not found"})
            return
        if not self.headers.get("Origin") or not self._origin_allowed():
            self.send_json(403, {"error": "origin not allowed"})
            return
        self.send_response(204)
        self._set_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._origin_allowed():
            self.send_json(403, {"error": "origin not allowed"})
            return
        path = urlparse(self.path)
        if path.path == "/api/status":
            worker_ready = bool(load_worker_url())
            self.send_json(200, {
                "game_running": game_is_running(),
                "queue_ready": worker_ready,
                "queue_worker_url": load_worker_url(),
            })
            return
        if path.path == "/api/queue/status":
            query = parse_qs(path.query)
            payload = {
                "token": query.get("token", [""])[0],
                "mode": query.get("mode", ["Duelo individual"])[0],
                "region": query.get("region", ["Sudamérica"])[0],
            }
            status, data = call_worker("status", payload)
            self.send_json(status, data)
            return
        if path.path == "/api/game/status":
            query = parse_qs(path.query)
            match_id = query.get("match_id", [""])[0]
            if not re.fullmatch(r"[a-f0-9-]{36}", match_id, re.I):
                self.send_json(400, {"error": "match_id inválido"})
                return
            try:
                parts = GAME_STATUS_PATH.read_text(encoding="ascii").strip().split("|", 4)
            except OSError:
                self.send_json(200, {"state": "starting"})
                return
            if len(parts) != 5 or parts[2] != match_id:
                self.send_json(200, {"state": "starting"})
                return
            phase, role, _match_id, token, value = parts
            payload = {"token": token, "mode": query.get("mode", ["Duelo individual"])[0], "region": query.get("region", ["Sudamérica"])[0]}
            if phase == "code" and role == "host":
                payload["code"] = value
                status, data = call_worker("code", payload)
                self.send_json(status, {"state": "code_shared" if status < 400 else "starting", **data})
                return
            if phase == "result":
                payload["winner_role"] = value
                status, data = call_worker("result", payload)
                self.send_json(status, data)
                return
            self.send_json(200, {"state": phase})
            return
        super().do_GET()

    def do_POST(self):
        if not self._origin_allowed():
            self.send_json(403, {"error": "origin not allowed"})
            return
        path = urlparse(self.path).path
        if path == "/api/game/start":
            if not self._origin_allowed():
                self.send_json(403, {"error": "origin not allowed"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 2 or length > 4096:
                    raise ValueError("invalid body size")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                token, match_id = str(payload.get("token", "")), str(payload.get("match_id", ""))
                role, code = str(payload.get("role", "")), str(payload.get("code", "")).upper()
                if not re.fullmatch(r"[a-f0-9-]{36}", token, re.I) or not re.fullmatch(r"[a-f0-9-]{36}", match_id, re.I):
                    raise ValueError("invalid match credentials")
                if role not in {"host", "join"} or (role == "join" and not re.fullmatch(r"[A-Z0-9]{6}", code)):
                    raise ValueError("invalid game role or room code")
            except (ValueError, AttributeError, UnicodeDecodeError, json.JSONDecodeError):
                self.send_json(400, {"error": "solicitud inválida"})
                return
            if not game_is_running():
                self.send_json(409, {"error": "Abrí Tenkaichi3Decomp.exe para iniciar la partida"})
                return
            IPC_DIR.mkdir(parents=True, exist_ok=True)
            command = f"{role}|{match_id}|{token}" if role == "host" else f"join|{code}|{match_id}|{token}"
            try:
                temporary = COMMAND_PATH.with_suffix(".tmp")
                temporary.write_text(command + "\n", encoding="ascii")
                temporary.replace(COMMAND_PATH)
            except OSError as error:
                self.send_json(500, {"error": f"No se pudo enviar la orden al juego: {error}"})
                return
            status, data = call_worker("start", {"token": token, "mode": payload.get("mode", "Duelo individual"), "region": payload.get("region", "Sudamérica")})
            self.send_json(status, data)
            return
        if not path.startswith("/api/queue/"):
            self.send_json(404, {"error": "not found"})
            return
        action = path.rsplit("/", 1)[-1]
        if action not in ALLOWED_ACTIONS or action == "status":
            self.send_json(404, {"error": "unknown action"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 4096:
                raise ValueError("invalid body size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("invalid payload")
            token = str(payload.get("token", ""))
            if len(token) != 36:
                raise ValueError("missing session token")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "solicitud inválida"})
            return

        if action in {"join", "accept", "code"} and not game_is_running():
            self.send_json(409, {"error": "Abrí Tenkaichi3Decomp.exe antes de buscar o aceptar"})
            return
        status, data = call_worker(action, payload)
        self.send_json(status, data)


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
        server.daemon_threads = True
    except OSError as error:
        print(f"No se pudo abrir http://{HOST}:{PORT}: {error}")
        input("Presioná Enter para cerrar...")
        raise SystemExit(1)
    print(f"Z-Arena listo en http://{HOST}:{PORT}", flush=True)
    print("Esta ventana sirve la página y comunica la cola con Cloudflare. Ctrl+C para cerrar.", flush=True)
    print("La cola necesita que z-arena-config.json tenga la URL del Worker.", flush=True)
    print(f"Canal local del juego: {IPC_DIR}", flush=True)
    threading.Thread(target=monitor_game_ipc, name="z-arena-game-bridge", daemon=True).start()
    threading.Timer(0.8, lambda: webbrowser.open(f"http://{HOST}:{PORT}/")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nZ-Arena cerrado.")
    finally:
        server.server_close()
