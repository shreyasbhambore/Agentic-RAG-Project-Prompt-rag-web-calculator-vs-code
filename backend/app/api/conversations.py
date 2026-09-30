"""Authenticated conversation history endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.conversations.service import (
    ConversationNotFound,
    append_message,
    create_conversation,
    get_conversation,
    list_conversations,
)
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/conversations", tags=["conversations"])
DbSession = Annotated[Session, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


class CreateConversationResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    agent: str | None = None
    sources: list[dict[str, str]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(CreateConversationResponse):
    messages: list[MessageResponse]


class CreateMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content must not be blank.")
        return value


@router.post(
    "",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    db: DbSession,
    current_user: AuthenticatedUser,
) -> CreateConversationResponse:
    return create_conversation(db, current_user.id)


@router.get("", response_model=list[CreateConversationResponse])
def list_owned(
    db: DbSession,
    current_user: AuthenticatedUser,
) -> list[CreateConversationResponse]:
    return list_conversations(db, current_user.id)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_one(
    conversation_id: str,
    db: DbSession,
    current_user: AuthenticatedUser,
) -> ConversationResponse:
    try:
        return get_conversation(db, current_user.id, conversation_id)
    except ConversationNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.") from error


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_user_message(
    conversation_id: str,
    payload: CreateMessageRequest,
    db: DbSession,
    current_user: AuthenticatedUser,
) -> MessageResponse:
    try:
        return append_message(
            db,
            current_user.id,
            conversation_id,
            payload.content,
            role="user",
        )
    except ConversationNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.") from error
