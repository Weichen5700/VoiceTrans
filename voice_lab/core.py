from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    MAX_IMPORT_BYTES,
    MAX_MODEL_BYTES,
    MAX_SEGMENT_SECONDS,
    MIN_SEGMENT_SECONDS,
    PROJECT_ROOT,
    get_data_root,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def append_activity(data_root: Path, action: str, details: dict[str, Any] | None = None) -> None:
    _append_jsonl(
        data_root / "activity.jsonl",
        {"timestamp": utc_now(), "action": action, "details": details or {}},
    )


def create_run(data_root: Path, operation: str, settings: dict[str, Any] | None = None) -> tuple[str, Path]:
    run_id = new_run_id()
    run_dir = data_root / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=False)
    _write_json(
        logs_dir / "run.json",
        {
            "run_id": run_id,
            "operation": operation,
            "status": "running",
            "started_at": utc_now(),
            "settings": settings or {},
            "app_version": "0.1.0",
        },
    )
    (logs_dir / "progress.log").write_text(
        f"[{utc_now()}] START operation={operation} run_id={run_id}\n", encoding="utf-8"
    )
    return run_id, run_dir


def log_progress(run_dir: Path, message: str, level: str = "INFO") -> None:
    with (run_dir / "logs" / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_now()}] {level} {message}\n")


def finish_run(
    run_dir: Path,
    status: str,
    summary: str,
    error: str | None = None,
) -> None:
    run_path = run_dir / "logs" / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run.update({"status": status, "finished_at": utc_now(), "summary": summary})
    if error:
        run["error"] = error
    _write_json(run_path, run)
    log_progress(run_dir, f"{status.upper()} {summary}", "ERROR" if error else "INFO")
    diagnosis = [
        "# 診斷摘要",
        "",
        f"- run-id：`{run['run_id']}`",
        f"- 操作：`{run['operation']}`",
        f"- 狀態：`{status}`",
        f"- 開始：`{run['started_at']}`",
        f"- 結束：`{run.get('finished_at', '未完成')}`",
        f"- 摘要：{summary}",
    ]
    if error:
        diagnosis.extend(["", "## 錯誤", "", f"```text\n{error}\n```"])
    diagnosis.extend(["", "## 下一步", "", "先查看 `progress.log`、`stdout.log` 及 `stderr.log`，再把本檔案複製給 LLM。"])
    (run_dir / "logs" / "diagnosis.md").write_text("\n".join(diagnosis) + "\n", encoding="utf-8")


def safe_error(exc: BaseException) -> str:
    """錯誤回報不包含環境變數、Token 或完整命令列。"""
    text = str(exc).strip() or exc.__class__.__name__
    for secret_name in ("OPENAI_API_KEY", "HF_TOKEN", "HF_API_TOKEN", "YOUTUBE_COOKIE"):
        secret = os.environ.get(secret_name)
        if secret:
            text = text.replace(secret, "<REDACTED>")
    return text[:2000]


def check_environment(data_root: Path) -> dict[str, Any]:
    data_root.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    checks = {
        "python": {"status": "PASS", "version": platform.python_version(), "path": sys.executable},
        "ffmpeg": {"status": "PASS" if ffmpeg else "BLOCKED", "path": ffmpeg},
        "ffprobe": {"status": "PASS" if ffprobe else "WARNING", "path": ffprobe},
        "data_root": {
            "status": "PASS" if os.access(data_root, os.W_OK) else "BLOCKED",
            "path": str(data_root),
        },
        "model_policy": {
            "status": "PASS",
            "max_bytes": MAX_MODEL_BYTES,
            "max_gib": 4,
            "download_default": "disabled",
        },
    }
    return {
        "checked_at": utc_now(),
        "app_version": "0.1.0",
        "project_root": str(PROJECT_ROOT),
        "checks": checks,
        "ready_without_models": bool(ffmpeg and checks["data_root"]["status"] == "PASS"),
    }


def create_startup_report(data_root: Path) -> dict[str, Any]:
    run_id, run_dir = create_run(data_root, "doctor")
    result = check_environment(data_root)
    _write_json(run_dir / "logs" / "environment.json", result)
    (run_dir / "logs" / "doctor.log").write_text(
        "\n".join(f"{name}: {item['status']}" for name, item in result["checks"].items()) + "\n",
        encoding="utf-8",
    )
    finish_run(run_dir, "succeeded", "環境檢查完成；模型下載預設關閉。")
    result["run_id"] = run_id
    result["report_dir"] = str(run_dir / "logs")
    return result


def load_project(data_root: Path) -> dict[str, Any] | None:
    path = data_root / "project.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def create_project(data_root: Path, name: str, language: str = "中文", voice_code: str = "voice-01") -> dict[str, Any]:
    clean_name = " ".join(name.strip().split())[:80]
    if not clean_name:
        raise ValueError("專案名稱不能空白。")
    project = {
        "project_id": uuid.uuid4().hex[:12],
        "name": clean_name,
        "language": language.strip()[:32] or "中文",
        "voice_code": voice_code.strip()[:64] or "voice-01",
        "created_at": utc_now(),
        "data_root": str(data_root),
        "version": 1,
    }
    _write_json(data_root / "project.json", project)
    append_activity(data_root, "project.created", {"project_id": project["project_id"]})
    return project


def resolve_input_file(raw_path: str) -> Path:
    path = Path(raw_path.strip().strip('"')).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"找不到本機檔案：{path}")
    size = path.stat().st_size
    if size > MAX_IMPORT_BYTES:
        raise ValueError("輸入檔超過第一版 2 GiB 上限，請先在外部裁切。")
    return path


def register_source(data_root: Path, raw_path: str) -> dict[str, Any]:
    path = resolve_input_file(raw_path)
    source = {
        "source_id": uuid.uuid4().hex[:12],
        "path": str(path),
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "registered_at": utc_now(),
    }
    _append_jsonl(data_root / "sources.jsonl", source)
    append_activity(data_root, "source.registered", {"source_id": source["source_id"], "name": path.name})
    return source


def run_command(command: list[str], run_dir: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    (run_dir / "logs" / "stdout.log").write_text(result.stdout[-200_000:], encoding="utf-8")
    (run_dir / "logs" / "stderr.log").write_text(result.stderr[-200_000:], encoding="utf-8")
    return result


def probe_media(data_root: Path, raw_path: str) -> dict[str, Any]:
    path = resolve_input_file(raw_path)
    run_id, run_dir = create_run(data_root, "media.inspect", {"path_name": path.name})
    ffprobe = shutil.which("ffprobe")
    result: dict[str, Any] = {"run_id": run_id, "path": str(path), "size_bytes": path.stat().st_size}
    if not ffprobe:
        result["status"] = "partial"
        result["message"] = "找不到 ffprobe，只能取得檔案大小；請安裝 FFmpeg 後重試。"
        finish_run(run_dir, "succeeded", result["message"])
        return result
    command = [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=index,codec_type,channels,sample_rate", "-of", "json", str(path)]
    completed = run_command(command, run_dir)
    if completed.returncode != 0:
        error = completed.stderr.strip()[-2000:] or "ffprobe 未提供錯誤訊息。"
        finish_run(run_dir, "failed", "媒體探測失敗。", safe_error(RuntimeError(error)))
        raise RuntimeError(error)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        finish_run(run_dir, "failed", "ffprobe 回傳格式無法解析。", safe_error(exc))
        raise RuntimeError("ffprobe 回傳格式無法解析。") from exc
    result.update(payload)
    result["status"] = "succeeded"
    finish_run(run_dir, "succeeded", "媒體探測完成。")
    return result


def convert_to_wav(data_root: Path, raw_path: str, start: float = 0, duration: float | None = None, preset: str = "original") -> dict[str, Any]:
    path = resolve_input_file(raw_path)
    if start < 0:
        raise ValueError("起始秒數不能小於 0。")
    if duration is not None and (duration < MIN_SEGMENT_SECONDS or duration > MAX_SEGMENT_SECONDS):
        raise ValueError(f"第一版輸出片段長度必須介於 {MIN_SEGMENT_SECONDS:g} 秒與 {MAX_SEGMENT_SECONDS:g} 秒。")
    if preset not in {"original", "light"}:
        raise ValueError("清理方式只能是 original 或 light。")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("找不到 ffmpeg；請先安裝 FFmpeg 並確認 PATH。")
    settings = {"path_name": path.name, "start": start, "duration": duration, "preset": preset}
    run_id, run_dir = create_run(data_root, "media.wav", settings)
    output_dir = data_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{run_id}.wav"
    temp_output = output.with_suffix(".part.wav")
    command = [ffmpeg, "-hide_banner", "-y", "-ss", str(start), "-i", str(path)]
    if duration is not None:
        command.extend(["-t", str(duration)])
    command.extend(["-vn"])
    if preset == "light":
        command.extend(["-af", "highpass=f=70,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11"])
    command.extend(["-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(temp_output)])
    try:
        completed = run_command(command, run_dir)
        if completed.returncode != 0 or not temp_output.exists() or temp_output.stat().st_size == 0:
            error = completed.stderr.strip()[-2000:] or "FFmpeg 沒有產生輸出檔。"
            finish_run(run_dir, "failed", "WAV 輸出失敗。", safe_error(RuntimeError(error)))
            raise RuntimeError(error)
        temp_output.replace(output)
        result = {"run_id": run_id, "status": "succeeded", "output": str(output), "size_bytes": output.stat().st_size, "preset": preset}
        _write_json(run_dir / "result.json", result)
        finish_run(run_dir, "succeeded", f"WAV 已輸出：{output.name}。")
        append_activity(data_root, "wav.created", {"run_id": run_id, "preset": preset})
        return result
    except Exception:
        if temp_output.exists():
            temp_output.unlink()
        raise


def validate_model_size(size_bytes: int | None, label: str = "model") -> dict[str, Any]:
    if size_bytes is None:
        return {"allowed": False, "status": "NEEDS_CHECK", "label": label, "reason": "大小未知，下載前必須取得 Content-Length 或以 4 GiB 串流上限保護。"}
    if size_bytes < 0:
        return {"allowed": False, "status": "BLOCKED", "label": label, "reason": "模型大小不能為負數。"}
    if size_bytes > MAX_MODEL_BYTES:
        return {"allowed": False, "status": "BLOCKED", "label": label, "reason": "模型超過 4 GiB 上限，禁止下載。", "size_bytes": size_bytes, "max_bytes": MAX_MODEL_BYTES}
    return {"allowed": True, "status": "PASS", "label": label, "reason": "模型大小未超過 4 GiB；第一版仍不自動下載。", "size_bytes": size_bytes, "max_bytes": MAX_MODEL_BYTES}


def list_runs(data_root: Path) -> list[dict[str, Any]]:
    root = data_root / "runs"
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for run_path in sorted(root.iterdir(), reverse=True):
        run_file = run_path / "logs" / "run.json"
        if run_file.exists():
            items.append(json.loads(run_file.read_text(encoding="utf-8")))
    return items[:30]
