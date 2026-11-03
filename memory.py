from typing import Sequence

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage
from langchain_postgres import PostgresChatMessageHistory

from database import pool

TABLE_NAME = "chat_message_history"

# cria tabela apenas uma vez no startup
with pool.connection() as conn:
    PostgresChatMessageHistory.create_tables(conn, TABLE_NAME)


class PooledChatMessageHistory(BaseChatMessageHistory):
    """Histórico no Postgres que pega uma conexão do pool a cada operação.

    O PostgresChatMessageHistory guarda a conexão que recebe; se ela caísse,
    ficaria quebrada para sempre. Aqui a conexão só vive durante a operação.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id

    def _history(self, conn) -> PostgresChatMessageHistory:
        return PostgresChatMessageHistory(
            TABLE_NAME, self.session_id, sync_connection=conn
        )

    @property
    def messages(self) -> list[BaseMessage]:
        with pool.connection() as conn:
            return self._history(conn).messages

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        with pool.connection() as conn:
            self._history(conn).add_messages(messages)

    def clear(self) -> None:
        with pool.connection() as conn:
            self._history(conn).clear()


def get_memory(session_id: str):
    return PooledChatMessageHistory(session_id)
