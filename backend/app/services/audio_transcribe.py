"""Локальное распознавание речи через Vosk (без внешних API)."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

from fastapi import HTTPException, status

from app.config import settings

_model_lock = threading.Lock()
_model = None

_ffmpeg_resolved: str | None = None


def _get_vosk_model():
    global _model
    if _model is not None:
        return _model

    model_path = (settings.vosk_model_path or "").strip()
    if not model_path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Распознавание не настроено: скачайте русскую модель Vosk "
                "(например vosk-model-small-ru-0.22 с https://alphacephei.com/vosk/models), "
                "распакуйте и задайте VOSK_MODEL_PATH — абсолютный путь к каталогу модели."
            ),
        )
    p = Path(model_path)
    if not p.is_dir():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"VOSK_MODEL_PATH не является каталогом: {model_path}",
        )

    from vosk import Model

    with _model_lock:
        if _model is None:
            try:
                _model = Model(str(p.resolve()))
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Не удалось загрузить модель Vosk: {e!s}",
                ) from e
    return _model


def _clear_ffmpeg_cache() -> None:
    global _ffmpeg_resolved
    _ffmpeg_resolved = None


def _candidate_paths_for_ffmpeg() -> list[str]:
    """Порядок: настройка → PATH → типичные пути Linux/Docker → Windows → imageio."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str | None) -> None:
        if not raw:
            return
        s = str(raw).strip()
        if not s or s in seen:
            return
        seen.add(s)
        out.append(s)

    add((settings.ffmpeg_path or "").strip() or None)
    add(shutil.which("ffmpeg"))

    if sys.platform != "win32":
        add("/usr/bin/ffmpeg")
        add("/usr/local/bin/ffmpeg")

    if sys.platform == "win32":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            if not base:
                continue
            root = Path(base)
            for tail in (
                Path("Gyan") / "FFmpeg" / "bin" / "ffmpeg.exe",
                Path("ffmpeg") / "bin" / "ffmpeg.exe",
            ):
                add(str(root / tail))

    try:
        import imageio_ffmpeg

        add(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    return out


def _path_if_executable(raw: str) -> Path | None:
    """Проверяет, что это реальный исполняемый файл (не голый 'ffmpeg' без PATH)."""
    p = Path(raw)
    if p.is_absolute():
        if p.is_file() and os.access(p, os.X_OK):
            return p.resolve()
        return None
    w = shutil.which(raw)
    if w:
        wp = Path(w)
        if wp.is_file() and os.access(wp, os.X_OK):
            return wp.resolve()
    return None


def _resolve_ffmpeg_executable() -> str:
    global _ffmpeg_resolved
    if _ffmpeg_resolved is not None:
        ok = _path_if_executable(_ffmpeg_resolved)
        if ok is not None:
            _ffmpeg_resolved = str(ok)
            return _ffmpeg_resolved
        _ffmpeg_resolved = None

    for cand in _candidate_paths_for_ffmpeg():
        ok = _path_if_executable(cand)
        if ok is not None:
            _ffmpeg_resolved = str(ok)
            return _ffmpeg_resolved

    raise RuntimeError(
        "Не найден рабочий ffmpeg. Запуск в Docker: выполните в корне проекта "
        "`docker compose build --no-cache api` и `docker compose up -d` (в образе уже есть /usr/bin/ffmpeg). "
        "Без Docker: `pip install -r requirements.txt` (imageio-ffmpeg) или установите ffmpeg в систему."
    )


def _ffmpeg_to_wav_16k_mono(src: Path) -> Path:
    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    out = Path(out_path)
    try:
        proc = subprocess.run(
            [
                _resolve_ffmpeg_executable(),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(out),
            ],
            capture_output=True,
            timeout=600,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(err or f"ffmpeg завершился с кодом {proc.returncode}")
        if not out.is_file() or out.stat().st_size < 64:
            raise RuntimeError("Не удалось получить WAV после конвертации")
        return out
    except FileNotFoundError:
        out.unlink(missing_ok=True)
        _clear_ffmpeg_cache()
        raise RuntimeError(
            "ffmpeg пропал после запуска (редко). Перезапустите API; в Docker — "
            "`docker compose build --no-cache api && docker compose up -d`."
        ) from None
    except subprocess.TimeoutExpired:
        out.unlink(missing_ok=True)
        raise RuntimeError("Конвертация аудио заняла слишком много времени") from None


def _recognize_wav_vosk(wav_path: Path, model) -> str:
    from vosk import KaldiRecognizer

    parts: list[str] = []
    with wave.open(str(wav_path), "rb") as wf:
        if wf.getnchannels() != 1:
            raise RuntimeError("После конвертации ожидался монофонический WAV")
        if wf.getsampwidth() != 2:
            raise RuntimeError("Ожидался 16-bit PCM")
        if wf.getcomptype() != "NONE":
            raise RuntimeError("Сжатый WAV не поддерживается")

        rec = KaldiRecognizer(model, wf.getframerate())
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                chunk = json.loads(rec.Result())
                t = (chunk.get("text") or "").strip()
                if t:
                    parts.append(t)

        final = json.loads(rec.FinalResult())
        t = (final.get("text") or "").strip()
        if t:
            parts.append(t)

    return " ".join(parts).strip()


def _transcribe_sync(
    path: Path,
    *,
    filename: str,
    content_type: str | None,
) -> str:
    ct = (content_type or "").lower()
    if not ct.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл не похож на аудио",
        )
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден на диске")

    size = path.stat().st_size
    if size > settings.max_attachment_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой")

    wav_temp: Path | None = None
    try:
        wav_temp = _ffmpeg_to_wav_16k_mono(path)
        model = _get_vosk_model()
        return _recognize_wav_vosk(wav_temp, model)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка распознавания: {e!s}",
        ) from e
    finally:
        if wav_temp is not None:
            wav_temp.unlink(missing_ok=True)


async def transcribe_audio_file(
    path: Path,
    *,
    filename: str,
    content_type: str | None,
) -> str:
    return await asyncio.to_thread(_transcribe_sync, path, filename=filename, content_type=content_type)
