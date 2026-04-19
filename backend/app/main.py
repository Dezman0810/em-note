from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, folders, mail, notes, shares, tags, user_settings
from app.config import settings
from app.sqlite_patch import apply_sqlite_folder_schema, ensure_note_accent_column


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401 - register metadata

    from app.database import engine
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(ensure_note_accent_column)
        if settings.database_url.startswith("sqlite"):
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(apply_sqlite_folder_schema)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(folders.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(shares.router, prefix="/api")
app.include_router(mail.router, prefix="/api")
app.include_router(user_settings.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
