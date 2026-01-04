from langchain_postgres import PostgresChatMessageHistory
from database import connection

TABLE_NAME = "chat_message_history"

# cria tabela apenas uma vez no startup
PostgresChatMessageHistory.create_tables(
    connection,
    TABLE_NAME
)

def get_memory(session_id: str):
    return PostgresChatMessageHistory(
        TABLE_NAME,
        session_id,
        sync_connection=connection
    )

