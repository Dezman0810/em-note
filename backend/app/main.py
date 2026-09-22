from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    admin,
    attachments,
    auth,
    budget,
    folders,
    grammar,
    habits,
    mail,
    note_filter_presets,
    note_public_links,
    note_diagrams,
    note_mindmaps,
    note_schemas,
    notes,
    public_notes,
    shares,
    tags,
    user_contacts,
    user_settings,
)
from app.alembic_startup import alembic_upgrade_head_at_startup
from app.config import settings
from app.utils.gzip_json import JsonGZipMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401 — register SQLAlchemy models

    alembic_upgrade_head_at_startup()

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Тело заметки бывает мегабайтным (картинки внутри content_json) — отдаём сжатым.
# За Nginx (прод) сжатие делает он, и флаг выключают: на одном ядре лишний gzip заметен.
if settings.gzip_json:
    app.add_middleware(JsonGZipMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(folders.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(note_filter_presets.router, prefix="/api")
app.include_router(shares.router, prefix="/api")
app.include_router(note_public_links.router, prefix="/api")
app.include_router(public_notes.router, prefix="/api")
app.include_router(mail.router, prefix="/api")
app.include_router(user_contacts.router, prefix="/api")
app.include_router(habits.router, prefix="/api")
app.include_router(grammar.router, prefix="/api")
app.include_router(budget.router, prefix="/api")
app.include_router(note_schemas.router, prefix="/api")
app.include_router(note_mindmaps.router, prefix="/api")
app.include_router(note_diagrams.router, prefix="/api")
app.include_router(user_settings.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/features")
async def features() -> dict[str, bool]:
    """Что включено на этом сервере: фронт прячет кнопки недоступных функций."""
    return {
        "audio_transcribe": bool(settings.vosk_enabled and settings.vosk_model_path.strip()),
    }
