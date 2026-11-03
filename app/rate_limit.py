import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request

from app import settings


def get_client_ip(request: Request) -> str:
    """No Render o IP real vem como primeiro valor de X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.TIMEZONE)


def today() -> date:
    return datetime.now(_tz()).date()


def next_reset() -> datetime:
    tomorrow = datetime.now(_tz()).date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=_tz())


def seconds_until_reset() -> int:
    return max(1, int((next_reset() - datetime.now(_tz())).total_seconds()))


class MinuteLimiter:
    """Janela deslizante de 60s em memória. Perder o estado num restart não importa."""

    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> tuple[bool, int]:
        """Só verifica, sem registrar. Devolve (ok, retry_after)."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= limit:
                return False, max(1, int(60 - (now - hits[0])) + 1)
            return True, 0

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def hit(self, key: str, limit: int) -> tuple[bool, int]:
        """Verifica e registra de forma atômica."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= limit:
                return False, max(1, int(60 - (now - hits[0])) + 1)
            hits.append(now)
            return True, 0

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if not hits:
            # evita crescer indefinidamente com IPs que não voltam
            self._hits.pop(key, None)
            return self._hits[key]
        return hits


class DailyCounterRepository:
    """Contadores diários no Postgres (sobrevivem ao sleep/restart do Render)."""

    def __init__(self, pool):
        self.pool = pool
        self._ensure_table()

    # `pool.connection()` faz commit ao sair do bloco e rollback se houver exceção.

    def _ensure_table(self):
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_daily (
                    scope TEXT NOT NULL,
                    key   TEXT NOT NULL,
                    day   DATE NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scope, key, day)
                )
                """
            )

    def increment(self, scope: str, key: str, day: date, limit: int) -> int | None:
        """Incrementa atomicamente. Devolve o novo valor, ou None se estourou o limite."""
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rate_limit_daily (scope, key, day, count)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (scope, key, day)
                DO UPDATE SET count = rate_limit_daily.count + 1
                WHERE rate_limit_daily.count < %s
                RETURNING count
                """,
                (scope, key, day, limit),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def refund(self, scope: str, key: str, day: date) -> None:
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE rate_limit_daily SET count = GREATEST(count - 1, 0)
                    WHERE scope = %s AND key = %s AND day = %s
                    """,
                    (scope, key, day),
                )
        except Exception:
            pass

    def get(self, scope: str, key: str, day: date) -> int:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count FROM rate_limit_daily WHERE scope = %s AND key = %s AND day = %s",
                (scope, key, day),
            )
            row = cur.fetchone()
        return row[0] if row else 0


def _too_many(detail: str, retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


class FreeTierGuard:
    GLOBAL_KEY = "all"

    def __init__(self, minute: MinuteLimiter, daily: DailyCounterRepository):
        self.minute = minute
        self.daily = daily

    def check(self, ip: str) -> int:
        """Consome 1 unidade da cota. Devolve quantas restam hoje para o IP."""
        for key, limit in (
            ("free:global", settings.FREE_GLOBAL_PER_MINUTE),
            (f"free:ip:{ip}", settings.FREE_USER_PER_MINUTE),
        ):
            ok, retry = self.minute.check(key, limit)
            if not ok:
                if key == "free:global":
                    raise _too_many(
                        "O modo gratuito está com muitos acessos agora. "
                        "Tente novamente em instantes ou use sua própria chave.",
                        retry,
                    )
                raise _too_many(
                    "Muitas mensagens em pouco tempo. Aguarde alguns segundos.", retry
                )

        day = today()
        reset_in = seconds_until_reset()

        if self.daily.increment("free_global", self.GLOBAL_KEY, day, settings.FREE_GLOBAL_PER_DAY) is None:
            raise _too_many(
                "O limite diário do modo gratuito foi atingido para todos os usuários. "
                "Volte amanhã ou use sua própria chave de API.",
                reset_in,
            )

        used = self.daily.increment("free_ip", ip, day, settings.FREE_USER_PER_DAY)
        if used is None:
            self.daily.refund("free_global", self.GLOBAL_KEY, day)
            raise _too_many(
                "Você atingiu o limite diário de mensagens gratuitas. "
                "Volte amanhã ou use sua própria chave de API.",
                reset_in,
            )

        self.minute.record("free:global")
        self.minute.record(f"free:ip:{ip}")
        return settings.FREE_USER_PER_DAY - used

    def refund(self, ip: str) -> None:
        """Devolve a cota quando a falha foi do provedor/servidor, não do usuário."""
        day = today()
        self.daily.refund("free_global", self.GLOBAL_KEY, day)
        self.daily.refund("free_ip", ip, day)

    def remaining(self, ip: str) -> int:
        used = self.daily.get("free_ip", ip, today())
        return max(0, settings.FREE_USER_PER_DAY - used)
