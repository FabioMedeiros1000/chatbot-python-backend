import uuid
from fastapi import HTTPException

from app.schemas import ChatbotRequest, ChatbotResponse, RoleResponse
from app.repositories import MessageRepository
from config import chat_config


class ChatbotService:
    def __init__(self, message_repository: MessageRepository):
        self.repository = message_repository

    async def get_response(
        self,
        payload: ChatbotRequest,
        api_key: str
    ) -> ChatbotResponse:
        session_id = payload.session_id or str(uuid.uuid4())

        try:
            chatbot = chat_config(api_key, payload.model_provider)

            chatbot.invoke(
                {"question": payload.question},
                config={"configurable": {"session_id": session_id}}
            )
        except Exception as e:
            error_text = str(e).lower()
            if "incorrect api key" in error_text or "invalid api key" in error_text:
                raise HTTPException(status_code=401, detail="A chave de API fornecida é inválida. Forneça uma chave válida!")
            else:
                raise HTTPException(status_code=401, detail=str(e))

        message = await self.repository.get_last_ai_message(session_id)

        return ChatbotResponse(
            id=message["id"],
            role=RoleResponse.assistant,
            content=message["content"],
            session_id=str(message["session_id"]),
            created_at=message["created_at"],
        )
    
    async def get_history(
        self,
        session_id: str,
        limit: int = 20,
        before_id: int | None = None
    ) -> list[ChatbotResponse]:

        rows = await self.repository.get_history_paginated(
            session_id=session_id,
            limit=limit,
            before_id=before_id
        )

        return [
            ChatbotResponse(
                id=row["id"],
                role=RoleResponse.assistant if row["role"] == "ai" else RoleResponse.human,
                content=row["content"],
                session_id=str(row["session_id"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
    
    async def delete_history(self, session_id: str) -> str:
        has_msgs = await self.repository.has_messages(session_id)
        if not has_msgs:
            raise HTTPException(
                status_code=404,
                detail=f"Nenhuma mensagem encontrada para a sessão {session_id}"
            )

        deleted_count = await self.repository.delete_by_session(session_id)
        return f"{deleted_count} mensagens deletadas"

