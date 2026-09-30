"""Streaming chat endpoint backed by authenticated conversation history."""

import json
import logging
from collections.abc import Iterator
from queue import Queue
from threading import Thread
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.runtime import AgentIdentity, AgentResponse, run_agent_request
from app.agents.supervisor import RouteTarget, default_route_decider
from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.conversations.service import (
    ConversationNotFound,
    append_message,
    create_conversation,
    get_conversation,
)
from app.database import get_db
from app.llm.groq import GroqConfigurationError, GroqStreamError
from app.models import Role, User
from app.tools.web_search import WebSearchError

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
DbSession = Annotated[Session, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


class StreamChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank.")
        return value


def _event(event_type: str, **values: Any) -> str:
    return f"data: {json.dumps({'type': event_type, **values}, ensure_ascii=False)}\n\n"


@router.post("/stream")
def stream_chat(
    payload: StreamChatRequest,
    db: DbSession,
    current_user: AuthenticatedUser,
) -> StreamingResponse:
    settings = get_settings()
    route = default_route_decider(payload.message)
    if route != RouteTarget.CALCULATOR and not settings.groq_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat streaming is not configured.",
        )

    try:
        conversation = (
            create_conversation(db, current_user.id)
            if payload.conversation_id is None
            else get_conversation(db, current_user.id, payload.conversation_id)
        )
    except ConversationNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error

    try:
        conversation = get_conversation(db, current_user.id, conversation.id)
        history = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages
        ]
        append_message(
            db,
            current_user.id,
            conversation.id,
            payload.message,
            role="user",
        )
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to persist the chat message.",
        ) from error

    def generate() -> Iterator[str]:
        events: Queue[tuple[str, Any]] = Queue()
        identity = AgentIdentity(
            id=current_user.id,
            role=Role(current_user.role),
        )

        def produce() -> None:
            try:
                result = run_agent_request(
                    payload.message,
                    identity,
                    history=history,
                    on_token=lambda token: events.put(("token", token)),
                )
                events.put(("result", result))
            except GroqStreamError as error:
                logger.warning(
                    "Groq request failed: category=%s status=%s",
                    error.failure_code,
                    error.status_code or "unavailable",
                )
                events.put(("error", error))
            except (
                GroqConfigurationError,
                WebSearchError,
                FileNotFoundError,
                PermissionError,
                ValueError,
                RuntimeError,
                OSError,
            ) as error:
                logger.warning("Agent request failed (%s).", type(error).__name__)
                events.put(("error", error))
            except Exception as error:
                logger.exception("Unexpected agent request failure.")
                events.put(("error", error))
            finally:
                events.put(("finished", None))

        worker = Thread(target=produce, daemon=True)
        worker.start()
        result: AgentResponse | None = None
        token_sent = False
        while True:
            event_type, value = events.get()
            if event_type == "finished":
                break
            if event_type == "token":
                token_sent = True
                yield _event("token", token=value)
            elif event_type == "result":
                result = value
            elif event_type == "error":
                if isinstance(value, GroqConfigurationError):
                    message = (
                        "Groq is not configured. Set GROQ_API_KEY in the project "
                        ".env file and restart FastAPI."
                    )
                elif isinstance(value, GroqStreamError):
                    message = _groq_error_message(value)
                elif isinstance(value, WebSearchError):
                    message = "Web search is unavailable or not configured."
                elif isinstance(value, FileNotFoundError):
                    message = "Document search is not ready; build the indexes first."
                else:
                    message = "Chat generation failed. Please try again."
                yield _event("error", message=message)
                return

        if result is None:
            yield _event("error", message="Chat generation failed. Please try again.")
            return
        if not token_sent:
            yield _event("token", token=result.response)
        try:
            assistant_message = append_message(
                db,
                current_user.id,
                conversation.id,
                result.response,
                role="assistant",
                agent=result.route,
                sources=result.sources,
            )
        except SQLAlchemyError:
            yield _event("error", message="Unable to save the assistant response.")
            return
        yield _event(
            "done",
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            agent=result.route,
            sources=result.sources,
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _groq_error_message(error: GroqStreamError) -> str:
    """Return actionable provider guidance without exposing provider payloads."""
    messages = {
        "unauthorized": (
            "Groq rejected the API key (HTTP 401). Check GROQ_API_KEY in .env; "
            "replace it if it was revoked, and restart FastAPI."
        ),
        "forbidden": (
            "Groq denied access (HTTP 403). Check that this account can use the "
            "configured model and that the model is available to your account."
        ),
        "not_found": (
            "Groq could not find the configured model (HTTP 404). Check GROQ_MODEL "
            "in .env and restart FastAPI."
        ),
        "rate_limited": (
            "Groq rate-limited this request (HTTP 429). Wait and retry, or check "
            "your Groq quota and billing."
        ),
        "timeout": "The request to Groq timed out. Check connectivity and retry.",
        "network": (
            "The backend could not connect to Groq. Check internet access, proxy, "
            "or firewall settings."
        ),
        "invalid_response": "Groq returned an invalid response. Retry the request.",
    }
    return messages.get(
        error.failure_code,
        "Groq could not complete the request. Check the backend terminal for its "
        "safe failure category, then retry.",
    )
