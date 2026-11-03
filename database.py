import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada")

# Pool em vez de conexão única: se o Postgres derrubar uma conexão ociosa
# (comum no Render), o pool descarta a morta e abre outra sozinho.
pool = ConnectionPool(
    DATABASE_URL,
    kwargs={"sslmode": "require"},
    min_size=1,
    max_size=5,
    max_idle=300,  # fecha conexões ociosas antes de o servidor derrubá-las
    check=ConnectionPool.check_connection,  # testa a conexão antes de entregá-la
    open=True,
)
