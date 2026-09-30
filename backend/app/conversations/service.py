"""Owner-scoped operations for persistent conversation history."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Conversation, ConversationMessage


class ConversationNotFound(LookupError):
    """Raised when a conversation is missing or owned by another user."""


def create_conversation(db: Session, user_id: str) -> Conversation:
    conversation = Conversation(user_id=user_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(db: Session, user_id: str) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id)
    )
    return list(db.scalars(statement).all())


def get_conversation(db: Session, user_id: str, conversation_id: str) -> Conversation:
    statement = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    conversation = db.scalar(statement)
    if conversation is None:
        raise ConversationNotFound("Conversation not found.")
    return conversation


def append_message(
    db: Session,
    user_id: str,
    conversation_id: str,
    content: str,
    role: str = "user",
    agent: str | None = None,
    sources: list[dict[str, str]] | None = None,
) -> ConversationMessage:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise ConversationNotFound("Conversation not found.")
    if role not in {"user", "assistant"}:
        raise ValueError("Message role must be 'user' or 'assistant'.")
    if role == "user" and (agent is not None or sources):
        raise ValueError("Agent and source metadata may only be stored on assistant messages.")

    message = ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        agent=agent,
        sources=sources if sources is not None else [],
    )
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
