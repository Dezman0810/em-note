"""Публичный список включённых функций и выключенное распознавание речи."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.config import settings
from app.services import audio_transcribe


async def test_features_follow_vosk_settings(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "vosk_enabled", True)
    monkeypatch.setattr(settings, "vosk_model_path", "")
    # Модели нет — распознавать нечем, даже если флаг включён.
    r = await client.get("/api/features")
    assert r.status_code == 200, r.text
    assert r.json() == {"audio_transcribe": False}

    monkeypatch.setattr(settings, "vosk_model_path", "/opt/vosk-model/vosk-model-small-ru-0.22")
    r = await client.get("/api/features")
    assert r.json() == {"audio_transcribe": True}

    monkeypatch.setattr(settings, "vosk_enabled", False)
    r = await client.get("/api/features")
    assert r.json() == {"audio_transcribe": False}


async def test_disabled_vosk_does_not_load_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "vosk_enabled", False)
    monkeypatch.setattr(settings, "vosk_model_path", "/opt/vosk-model/vosk-model-small-ru-0.22")
    monkeypatch.setattr(audio_transcribe, "_model", None)

    with pytest.raises(HTTPException) as err:
        audio_transcribe._get_vosk_model()
    assert err.value.status_code == 503
    assert "отключено" in err.value.detail
    assert audio_transcribe._model is None
