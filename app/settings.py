import os
from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Modo gratuito (chave Groq do servidor) ---
FREE_PROVIDER = os.getenv("FREE_PROVIDER", "groq")
FREE_MODEL = os.getenv("FREE_MODEL", "openai/gpt-oss-20b")
FREE_MAX_TOKENS = _int("FREE_MAX_TOKENS", 1024)
FREE_HISTORY_WINDOW = _int("FREE_HISTORY_WINDOW", 4)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Limites do modo gratuito ---
FREE_USER_PER_MINUTE = _int("FREE_USER_PER_MINUTE", 2)
FREE_USER_PER_DAY = _int("FREE_USER_PER_DAY", 10)
FREE_GLOBAL_PER_MINUTE = _int("FREE_GLOBAL_PER_MINUTE", 3)
FREE_GLOBAL_PER_DAY = _int("FREE_GLOBAL_PER_DAY", 70)

# --- Limites do modo BYOK (chave do usuário) ---
BYOK_USER_PER_MINUTE = _int("BYOK_USER_PER_MINUTE", 20)
BYOK_HISTORY_WINDOW = _int("BYOK_HISTORY_WINDOW", 20)

# --- Rota de modelos ---
MODELS_PER_MINUTE = _int("MODELS_PER_MINUTE", 30)
MODELS_CACHE_TTL_SECONDS = _int("MODELS_CACHE_TTL_SECONDS", 15 * 60)

# --- Entrada ---
MAX_QUESTION_CHARS = _int("MAX_QUESTION_CHARS", 4000)

# --- Fuso para virada do dia ---
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

# --- CORS ---
CORS_ORIGINS = _list(
    "CORS_ORIGINS",
    "https://chatbot-python-frontend.vercel.app,"
    "http://localhost:5173,http://127.0.0.1:5173",
)
