import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Tuple


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    question TEXT,
    answer TEXT
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self._ensure_db()

    def _ensure_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            conn.executescript(DB_SCHEMA)
            conn.commit()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def upsert_user(
        self, telegram_id: int, full_name: str, question: str, answer: str
    ) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_id, full_name, question, answer)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    question = excluded.question,
                    answer = excluded.answer
                """,
                (telegram_id, full_name, question, answer),
            )
            conn.commit()

    def get_user(self, telegram_id: int) -> Optional[Tuple[int, int, str, str, str]]:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT id, telegram_id, full_name, question, answer "
                "FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = cur.fetchone()
        return row

