from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class ModelProvider(str, Enum):
    chatgpt = "chatgpt"
    groq = "groq"

class RoleResponse(str, Enum):
    assistant = "assistant"
    human = "human"

class ChatbotRequest(BaseModel):
    question: str
    session_id: Optional[str] = Field(default=None)
    model_provider: ModelProvider

class ChatbotResponse(BaseModel):
    id: int                  
    role: RoleResponse       
    content: str             
    session_id: str
    created_at: datetime
