from fastapi import APIRouter, HTTPException, Header, Request, Response
from typing import Optional
from fastapi import Query
from starlette.concurrency import run_in_threadpool

from app import settings
from app.schemas import (
    ChatbotRequest,
    ChatbotResponse,
    ModelProvider,
    ModelsResponse,
    UsageResponse,
)
from database import pool
from app.repositories import MessageRepository
from app.services import ChatbotService
from app.providers import free_models, list_models
from app.rate_limit import (
    DailyCounterRepository,
    FreeTierGuard,
    MinuteLimiter,
    _too_many,
    get_client_ip,
    next_reset,
)

router = APIRouter(prefix="/api")
message_repository = MessageRepository(pool)
minute_limiter = MinuteLimiter()
free_guard = FreeTierGuard(minute_limiter, DailyCounterRepository(pool))
chatbot_service = ChatbotService(message_repository, free_guard, minute_limiter)


def _extract_api_key(authorization: Optional[str]) -> Optional[str]:
    """Chave opcional: sem Authorization (ou vazio) cai no modo gratuito."""
    if not authorization:
        return None
    key = authorization.removeprefix("Bearer ").strip()
    return key or None


@router.post("/chatbot", response_model=ChatbotResponse)
async def chatbot(
    payload: ChatbotRequest,
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="O parâmetro question é obrigatório")

    api_key = _extract_api_key(authorization)
    ip = get_client_ip(request)

    result, remaining = await chatbot_service.get_response(payload, api_key, ip)

    if remaining is not None:
        response.headers["X-RateLimit-Limit"] = str(settings.FREE_USER_PER_DAY)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

    return result


@router.get("/models/{provider}", response_model=ModelsResponse)
async def models(
    provider: ModelProvider,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    ip = get_client_ip(request)
    ok, retry = minute_limiter.hit(f"models:{ip}", settings.MODELS_PER_MINUTE)
    if not ok:
        raise _too_many("Muitas consultas de modelos. Aguarde alguns segundos.", retry)

    api_key = _extract_api_key(authorization)

    if not api_key:
        # sem chave só existe o modelo gratuito (Groq do servidor)
        if provider.value == settings.FREE_PROVIDER:
            return ModelsResponse(provider=provider, requires_key=True, models=free_models())
        return ModelsResponse(provider=provider, requires_key=True, models=[])

    return ModelsResponse(provider=provider, models=await list_models(provider, api_key))


@router.get("/usage", response_model=UsageResponse)
async def usage(request: Request):
    ip = get_client_ip(request)
    remaining = await run_in_threadpool(free_guard.remaining, ip)
    return UsageResponse(
        model=settings.FREE_MODEL,
        limit=settings.FREE_USER_PER_DAY,
        remaining=remaining,
        resets_at=next_reset(),
    )


@router.get("/history/{session_id}", response_model=list[ChatbotResponse])
async def history(
    session_id: str,
    limit: int = Query(20, le=50),
    before_id: Optional[int] = Query(None)
):
    return await chatbot_service.get_history(
        session_id=session_id,
        limit=limit,
        before_id=before_id
    )

@router.delete("/history/{session_id}", response_model=str)
async def delete_history(
    session_id: str
):
    return await chatbot_service.delete_history(
        session_id=session_id
    )
