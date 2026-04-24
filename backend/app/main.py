from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import health, brief
from app.routers.channels import text_channel, voice_channel, image_channel, whatsapp_channel


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: init DB connections, Firestore client, etc.
    yield
    # shutdown: cleanup


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core ──────────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api/v1")
app.include_router(brief.router, prefix="/api/v1")

# ── Intake channels (all funnel to intake_service.process_intake) ─────────────
app.include_router(text_channel.router, prefix="/api/v1")
app.include_router(voice_channel.router, prefix="/api/v1")
app.include_router(image_channel.router, prefix="/api/v1")
app.include_router(whatsapp_channel.router, prefix="/api/v1")  # Phase 5B stub