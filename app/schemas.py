from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

from app import settings

class ModelProvider(str, Enum):
    openai = "openai"
    groq = "groq"
    google = "google"

class RoleResponse(str, Enum):
    assistant = "assistant"
    human = "human"

class ChatbotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=settings.MAX_QUESTION_CHARS)
    session_id: Optional[str] = Field(default=None)
    # Ignorados no modo gratuito (sem Authorization); obrigatórios com chave própria
    model_provider: Optional[ModelProvider] = Field(default=None)
    model: Optional[str] = Field(default=None, max_length=100)

class ChatbotResponse(BaseModel):
    id: int
    role: RoleResponse
    content: str
    session_id: str
    created_at: datetime

class ModelInfo(BaseModel):
    id: str
    name: str
    free: bool = False

class ModelsResponse(BaseModel):
    provider: ModelProvider
    requires_key: bool = False
    models: list[ModelInfo]

class UsageResponse(BaseModel):
    model: str
    limit: int
    remaining: int
    resets_at: datetime
