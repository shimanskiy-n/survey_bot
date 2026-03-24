import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Tuple


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_text TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(telegram_id, question_id)
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self._ensure_db()

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cur.fetchone() is not None

    def _users_has_is_admin_column(self, conn: sqlite3.Connection) -> bool:
        cur = conn.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}  # row[1] = column name
        return "is_admin" in cols

    def _ensure_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            # Migration for old schema: old `users` had columns `question` and `answer`.
            if self._table_exists(conn, "users") and not self._users_has_is_admin_column(
                conn
            ):
                conn.execute("BEGIN")
                conn.execute(
                    """
                    CREATE TABLE users_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER UNIQUE NOT NULL,
                        full_name TEXT NOT NULL,
                        is_admin INTEGER NOT NULL DEFAULT 0
                    );
                    """
                )
                conn.execute(
                    """
                    INSERT INTO users_new (telegram_id, full_name, is_admin)
                    SELECT telegram_id, full_name, 0
                    FROM users
                    """
                )
                conn.execute("DROP TABLE users")
                conn.execute("ALTER TABLE users_new RENAME TO users")
                conn.commit()

            conn.executescript(DB_SCHEMA)
            conn.commit()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def count_users(self) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM users")
            (cnt,) = cur.fetchone()
            return int(cnt)

    def count_admins(self) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
            (cnt,) = cur.fetchone()
            return int(cnt)

    def set_user_admin(self, telegram_id: int, is_admin: bool) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE users SET is_admin = ? WHERE telegram_id = ?",
                (int(is_admin), telegram_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_user(self, telegram_id: int) -> Optional[Tuple[str, int]]:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT full_name, is_admin FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        full_name, is_admin = row
        return str(full_name), int(is_admin)

    def upsert_user(self, telegram_id: int, full_name: str, is_admin: int) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_id, full_name, is_admin)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    is_admin = users.is_admin
                """,
                (telegram_id, full_name, is_admin),
            )
            conn.commit()

    def get_next_question_sort_order(self) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM questions")
            (val,) = cur.fetchone()
            return int(val)

    def create_question(
        self, question_text: str, *, is_active: bool = True, sort_order: int | None = None
    ) -> int:
        if sort_order is None:
            sort_order = self.get_next_question_sort_order()
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO questions (question_text, is_active, sort_order)
                VALUES (?, ?, ?)
                """,
                (question_text, int(is_active), int(sort_order)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def set_question_active(self, question_id: int, is_active: bool) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE questions SET is_active = ? WHERE id = ?",
                (int(is_active), question_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_question_text(self, question_id: int) -> Optional[str]:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT question_text FROM questions WHERE id = ?",
                (question_id,),
            )
            row = cur.fetchone()
        return None if not row else str(row[0])

    def get_active_questions(self) -> list[Tuple[int, str]]:
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                SELECT id, question_text
                FROM questions
                WHERE is_active = 1
                ORDER BY sort_order ASC, id ASC
                """
            )
            rows = cur.fetchall()
        return [(int(q_id), str(text)) for q_id, text in rows]

    def list_questions(
        self,
    ) -> list[Tuple[int, str, int, int]]:
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                SELECT id, question_text, is_active, sort_order
                FROM questions
                ORDER BY sort_order ASC, id ASC
                """
            )
            rows = cur.fetchall()
        return [(int(q_id), str(text), int(active), int(order)) for q_id, text, active, order in rows]

    def upsert_answer(self, telegram_id: int, question_id: int, answer_text: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO answers (telegram_id, question_id, answer_text)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id, question_id) DO UPDATE SET
                    answer_text = excluded.answer_text,
                    created_at = datetime('now')
                """,
                (telegram_id, question_id, answer_text),
            )
            conn.commit()

