from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import MAX_JSON_BYTES, get_data_root
from .core import (
    check_environment,
    convert_to_wav,
    create_project,
    create_startup_report,
    list_runs,
    load_project,
    probe_media,
    register_source,
    safe_error,
    validate_model_size,
)


UI_ROOT = Path(__file__).resolve().parents[1] / "ui"


class AppState:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "VoiceLab/0.1"

    @property
    def state(self) -> AppState:
        return self.server.app_state  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[http] {self.address_string()} - {format % args}")

    def send_json(self, status: int, value: Any) -> None:
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_json(404, {"error": "找不到頁面。"})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.send_file(UI_ROOT / "index.html")
        if parsed.path.startswith("/static/"):
            relative = Path(parsed.path.removeprefix("/static/")).name
            return self.send_file(UI_ROOT / relative)
        if parsed.path == "/api/status":
            return self.send_json(200, check_environment(self.state.data_root))
        if parsed.path == "/api/project":
            return self.send_json(200, {"project": load_project(self.state.data_root)})
        if parsed.path == "/api/runs":
            return self.send_json(200, {"runs": list_runs(self.state.data_root)})
        self.send_json(404, {"error": "找不到 API。"})

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_JSON_BYTES:
            raise ValueError("請提供不超過 1 MiB 的 JSON 請求。")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("請求內容必須是 JSON 物件。")
        return payload

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/project":
                result = create_project(self.state.data_root, str(payload.get("name", "")), str(payload.get("language", "中文")), str(payload.get("voice_code", "voice-01")))
                return self.send_json(201, {"project": result})
            if parsed.path == "/api/media/register":
                result = register_source(self.state.data_root, str(payload.get("path", "")))
                return self.send_json(201, {"source": result})
            if parsed.path == "/api/media/inspect":
                result = probe_media(self.state.data_root, str(payload.get("path", "")))
                return self.send_json(200, {"media": result})
            if parsed.path == "/api/media/wav":
                duration = payload.get("duration")
                result = convert_to_wav(self.state.data_root, str(payload.get("path", "")), float(payload.get("start", 0)), float(duration) if duration not in (None, "") else None, str(payload.get("preset", "original")))
                return self.send_json(201, {"wav": result})
            if parsed.path == "/api/models/check":
                raw = payload.get("size_bytes")
                size = int(raw) if raw not in (None, "") else None
                return self.send_json(200, {"model": validate_model_size(size, str(payload.get("label", "model")))})
            self.send_json(404, {"error": "找不到 API。"})
        except Exception as exc:
            self.send_json(400, {"error": safe_error(exc)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Voice Lab 本機音訊研究工具")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="啟動本機瀏覽器介面")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--data-root", default=None)
    serve.add_argument("--no-browser", action="store_true")
    doctor = sub.add_parser("doctor", help="只執行環境檢查並輸出 Log")
    doctor.add_argument("--data-root", default=None)
    model = sub.add_parser("model-check", help="檢查模型大小，不下載模型")
    model.add_argument("size_bytes", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "serve"
    if command == "doctor":
        result = create_startup_report(get_data_root(args.data_root))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if command == "model-check":
        result = validate_model_size(args.size_bytes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["allowed"] else 2
    data_root = get_data_root(args.data_root)
    state = AppState(data_root)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.app_state = state  # type: ignore[attr-defined]
    url = f"http://{args.host}:{args.port}/"
    print(f"Voice Lab 已啟動：{url}")
    print(f"資料根目錄：{data_root}")
    print("模型下載：預設關閉；4 GiB 以上模型禁止下載。按 Ctrl+C 停止。")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nVoice Lab 已停止。")
    finally:
        httpd.server_close()
    return 0
