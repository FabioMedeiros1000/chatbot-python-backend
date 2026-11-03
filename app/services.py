import uuid
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app import settings
from app.schemas import ChatbotRequest, ChatbotResponse, RoleResponse
from app.repositories import MessageRepository
from app.providers import build_llm, build_free_llm, map_provider_error
from app.rate_limit import FreeTierGuard, MinuteLimiter, _too_many
from config import chat_config
from prompt import REFUSAL


class ChatbotService:
    def __init__(
        self,
        message_repository: MessageRepository,
        free_guard: FreeTierGuard,
        minute_limiter: MinuteLimiter,
    ):
        self.repository = message_repository
        self.free_guard = free_guard
        self.minute_limiter = minute_limiter

    async def get_response(
        self,
        payload: ChatbotRequest,
        api_key: str | None,
        ip: str,
    ) -> tuple[ChatbotResponse, int | None]:
        """Devolve (resposta, mensagens gratuitas restantes hoje | None se BYOK)."""
        session_id = payload.session_id or str(uuid.uuid4())
        free_mode = not api_key
        remaining = None

        if free_mode:
            # consome a cota antes de chamar o provedor
            remaining = await run_in_threadpool(self.free_guard.check, ip)
            llm = build_free_llm()
            history_window = settings.FREE_HISTORY_WINDOW
        else:
            if not payload.model_provider or not payload.model:
                raise HTTPException(
                    status_code=400,
                    detail="Informe o provedor e o modelo ao usar sua própria chave.",
                )
            ok, retry = self.minute_limiter.hit(f"byok:{ip}", settings.BYOK_USER_PER_MINUTE)
            if not ok:
                raise _too_many("Muitas mensagens em pouco tempo. Aguarde alguns segundos.", retry)
            llm = build_llm(payload.model_provider, payload.model, api_key)
            history_window = settings.BYOK_HISTORY_WINDOW

        try:
            chatbot = chat_config(llm, history_window, concise=free_mode)

            # invoke é síncrono (histórico usa conexão psycopg síncrona):
            # roda em thread para não travar o event loop
            await run_in_threadpool(
                chatbot.invoke,
                {"question": payload.question},
                config={"configurable": {"session_id": session_id}},
            )
        except Exception as e:
            error = map_provider_error(e)
            # falha do provedor/servidor não deve gastar a cota do usuário
            if free_mode and error.status_code in (429, 502, 400):
                await run_in_threadpool(self.free_guard.refund, ip)
            raise error

        message = await self.repository.get_last_ai_message(session_id)

        # Recusa (fora do escopo ou tentativa de injeção): não deixa a troca no
        # histórico, para não contaminar o contexto das próximas mensagens.
        # Continua contando na cota do modo gratuito.
        if message["content"].strip().startswith(REFUSAL):
            await self.repository.delete_last(session_id, 2)

        response = ChatbotResponse(
            id=message["id"],
            role=RoleResponse.assistant,
            content=message["content"],
            session_id=str(message["session_id"]),
            created_at=message["created_at"],
        )
        return response, remaining
    
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

