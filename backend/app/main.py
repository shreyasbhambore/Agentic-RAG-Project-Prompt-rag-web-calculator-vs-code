"""FastAPI entry point for the Agentic RAG backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine, inspect, text

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.config import get_settings
from app.database import Base, engine

settings = get_settings()


def ensure_conversation_message_metadata_schema(bind: Engine = engine) -> None:
    """Add agent/source columns to databases created before runtime integration."""
    if "conversation_messages" not in inspect(bind).get_table_names():
        return
    columns = {
        column["name"] for column in inspect(bind).get_columns("conversation_messages")
    }
    with bind.begin() as connection:
        if "agent" not in columns:
            connection.execute(
                text("ALTER TABLE conversation_messages ADD COLUMN agent VARCHAR(64)")
            )
        if "sources" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE conversation_messages "
                    "ADD COLUMN sources JSON NOT NULL DEFAULT '[]'"
                )
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_conversation_message_metadata_schema(engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(conversations_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a minimal readiness signal for the frontend and deployment checks."""
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}
