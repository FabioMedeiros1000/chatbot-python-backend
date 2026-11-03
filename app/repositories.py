class MessageRepository:
    def __init__(self, pool):
        self.pool = pool

    # `pool.connection()` faz commit ao sair do bloco e rollback se houver exceção.

    async def get_last_ai_message(self, session_id: str):
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    session_id,
                    message->'data'->>'content' AS content,
                    message->>'type' AS role,
                    created_at
                FROM chat_message_history
                WHERE session_id = %s
                    AND message->>'type' = 'ai'
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,)
            )
            row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "session_id": row[1],
            "content": row[2],
            "role": row[3],
            "created_at": row[4],
        }
    
    async def get_history_paginated(
        self,
        session_id: str,
        limit: int,
        before_id: int | None = None
    ):
        query = """
            SELECT
                id,
                session_id,
                message->'data'->>'content' AS content,
                message->>'type' AS role,
                created_at
            FROM chat_message_history
            WHERE session_id = %s
        """
        params = [session_id]

        if before_id:
            query += " AND id < %s"
            params.append(before_id)

        query += """
            ORDER BY id DESC
            LIMIT %s
        """
        params.append(limit)

        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        # Reverte para ordem cronológica no frontend
        rows.reverse()

        return [
            {
                "id": r[0],
                "session_id": r[1],
                "content": r[2],
                "role": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]
    
    async def has_messages(self, session_id: str) -> bool:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM chat_message_history WHERE session_id = %s LIMIT 1",
                (session_id,)
            )
            return cur.fetchone() is not None

    async def delete_last(self, session_id: str, n: int) -> int:
        """Apaga as n mensagens mais recentes da sessão (ex.: pergunta + recusa)."""
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM chat_message_history
                WHERE id IN (
                    SELECT id FROM chat_message_history
                    WHERE session_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                )
                RETURNING id
                """,
                (session_id, n)
            )
            deleted_rows = cur.fetchall()

        return len(deleted_rows)

    async def delete_by_session(self, session_id: str) -> int:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM chat_message_history
                WHERE session_id = %s
                RETURNING id
                """,
                (session_id,)
            )
            deleted_rows = cur.fetchall()

        return len(deleted_rows)
