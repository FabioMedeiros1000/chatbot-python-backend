import hashlib
import re
import time

import httpx
from fastapi import HTTPException
from langchain_openai import ChatOpenAI

from app import settings
from app.schemas import ModelInfo, ModelProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
GROQ_MODELS_URL = f"{GROQ_BASE_URL}/models"
GOOGLE_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


# ---------------------------------------------------------------- LLM builder

def build_llm(provider: ModelProvider, model: str, api_key: str, free_mode: bool = False):
    if provider == ModelProvider.openai:
        return ChatOpenAI(model=model, temperature=0.3, api_key=api_key)

    if provider == ModelProvider.groq:
        kwargs = {}
        if free_mode:
            kwargs["max_completion_tokens"] = settings.FREE_MAX_TOKENS
            kwargs["reasoning_effort"] = "low"
        return ChatOpenAI(
            model=model,
            temperature=0.3,
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            **kwargs,
        )

    if provider == ModelProvider.google:
        # import tardio: só carrega o SDK do Google se alguém usar o provedor
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, temperature=0.3, google_api_key=api_key)

    raise ValueError("Model provider não suportado")


def build_free_llm():
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="O modo gratuito está indisponível no momento. Use sua própria chave de API.",
        )
    return build_llm(
        ModelProvider(settings.FREE_PROVIDER),
        settings.FREE_MODEL,
        settings.GROQ_API_KEY,
        free_mode=True,
    )


# ---------------------------------------------------------------- error mapping

def map_provider_error(e: Exception) -> HTTPException:
    status = getattr(e, "status_code", None) or getattr(e, "code", None)
    if not isinstance(status, int):
        status = None
    text = str(e).lower()

    headers = None
    response = getattr(e, "response", None)
    retry_after = getattr(getattr(response, "headers", None), "get", lambda *_: None)("retry-after")
    if retry_after:
        headers = {"Retry-After": str(retry_after)}

    if status in (401, 403) or "api key" in text and ("invalid" in text or "incorrect" in text):
        return HTTPException(401, "A chave de API fornecida é inválida. Forneça uma chave válida!")
    if status == 404 or "model_not_found" in text or "does not exist" in text:
        return HTTPException(400, "Modelo não disponível para este provedor ou chave.")
    if "insufficient_quota" in text or "no credits" in text or "credit_balance" in text:
        return HTTPException(429, "A conta desta chave de API está sem créditos/cota no provedor.")
    if status == 429 or "rate limit" in text or "quota" in text:
        return HTTPException(429, "Limite do provedor atingido. Tente novamente em instantes.", headers=headers)
    return HTTPException(502, "Falha ao consultar o provedor do modelo. Tente novamente.")


# ---------------------------------------------------------------- list models

_OPENAI_KEEP = re.compile(r"^(gpt-|chatgpt-|o\d)")
# também descarta snapshots datados (gpt-4o-2024-08-06, gpt-4-0613): o alias sem data basta
_OPENAI_DROP = re.compile(
    r"audio|realtime|transcribe|tts|image|search|embedding|moderation|instruct|whisper|dall-e"
    r"|-\d{4}-\d{2}-\d{2}$|-\d{4}$"
)
_GROQ_DROP = re.compile(r"whisper|orpheus|guard|tts|embed")
_GOOGLE_DROP = re.compile(r"embedding|tts|image|live|aqa|imagen|veo")

_cache: dict[tuple[str, str], tuple[float, list[ModelInfo]]] = {}


def free_models() -> list[ModelInfo]:
    return [ModelInfo(id=settings.FREE_MODEL, name=settings.FREE_MODEL, free=True)]


async def list_models(provider: ModelProvider, api_key: str) -> list[ModelInfo]:
    key = (provider.value, hashlib.sha256(api_key.encode()).hexdigest())
    now = time.monotonic()

    cached = _cache.get(key)
    if cached and now - cached[0] < settings.MODELS_CACHE_TTL_SECONDS:
        return cached[1]

    models = await _fetch_models(provider, api_key)

    # limpa entradas vencidas para o cache não crescer sem limite
    for k in [k for k, (ts, _) in _cache.items() if now - ts >= settings.MODELS_CACHE_TTL_SECONDS]:
        _cache.pop(k, None)
    _cache[key] = (now, models)
    return models


async def _fetch_models(provider: ModelProvider, api_key: str) -> list[ModelInfo]:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            if provider == ModelProvider.openai:
                resp = await client.get(OPENAI_MODELS_URL, headers={"Authorization": f"Bearer {api_key}"})
            elif provider == ModelProvider.groq:
                resp = await client.get(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {api_key}"})
            else:
                resp = await client.get(
                    GOOGLE_MODELS_URL,
                    params={"pageSize": 1000},
                    headers={"x-goog-api-key": api_key},
                )
        except httpx.HTTPError:
            raise HTTPException(502, "Não foi possível consultar a lista de modelos do provedor.")

    if resp.status_code in (400, 401, 403):
        # Google devolve 400 para chave inválida
        raise HTTPException(401, "A chave de API fornecida é inválida. Forneça uma chave válida!")
    if resp.status_code == 429:
        raise HTTPException(429, "Limite do provedor atingido. Tente novamente em instantes.")
    if resp.status_code != 200:
        raise HTTPException(502, "Não foi possível consultar a lista de modelos do provedor.")

    data = resp.json()

    if provider == ModelProvider.openai:
        ids = [
            m["id"] for m in data.get("data", [])
            if _OPENAI_KEEP.match(m["id"]) and not _OPENAI_DROP.search(m["id"])
        ]
    elif provider == ModelProvider.groq:
        ids = [
            m["id"] for m in data.get("data", [])
            if m.get("active", True) and not _GROQ_DROP.search(m["id"])
        ]
    else:
        ids = []
        for m in data.get("models", []):
            name = m.get("name", "").removeprefix("models/")
            if (
                name.startswith("gemini")
                and "generateContent" in m.get("supportedGenerationMethods", [])
                and not _GOOGLE_DROP.search(name)
            ):
                ids.append(name)

    return [ModelInfo(id=i, name=i) for i in sorted(set(ids))]
