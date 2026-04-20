from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, auth, folders, mail, note_public_links, notes, public_notes, shares, tags, user_settings
from app.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401 — register SQLAlchemy models

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
app.include_router(admin.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(folders.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(shares.router, prefix="/api")
app.include_router(note_public_links.router, prefix="/api")
app.include_router(public_notes.router, prefix="/api")
app.include_router(mail.router, prefix="/api")
app.include_router(user_settings.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
