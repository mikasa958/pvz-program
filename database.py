from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


class GameDatabase:
    """SQLite storage for session summaries, per-tick state and actions."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else Path(__file__).resolve().parent / "logs" / "game_log.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                result TEXT NOT NULL,
                score INTEGER NOT NULL,
                survived_time REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_ticks (
                session_id INTEGER NOT NULL,
                tick INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                reward REAL NOT NULL,
                FOREIGN KEY(session_id) REFERENCES game_sessions(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                session_id INTEGER NOT NULL,
                tick INTEGER NOT NULL,
                action_id INTEGER NOT NULL,
                valid INTEGER NOT NULL,
                FOREIGN KEY(session_id) REFERENCES game_sessions(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_game_ticks_session
            ON game_ticks(session_id)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_actions_session
            ON actions(session_id)
            """
        )
        self.conn.commit()

    def create_session(
        self,
        mode: str,
        result: str = "running",
        score: int = 0,
        survived_time: float = 0.0,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO game_sessions (mode, result, score, survived_time)
            VALUES (?, ?, ?, ?)
            """,
            (mode, result, int(score), float(survived_time)),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def finalize_session(
        self,
        session_id: int,
        result: str,
        score: int,
        survived_time: float,
    ) -> None:
        self.conn.execute(
            """
            UPDATE game_sessions
            SET result = ?, score = ?, survived_time = ?
            WHERE id = ?
            """,
            (result, int(score), float(survived_time), int(session_id)),
        )
        self.conn.commit()

    def write_step_logs(self, session_id: int, rows: Iterable[dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return

        tick_rows: list[tuple[int, int, str, float]] = []
        action_rows: list[tuple[int, int, int, int]] = []

        for row in rows:
            tick_rows.append(
                (
                    int(session_id),
                    int(row["tick"]),
                    str(row["state_json"]),
                    float(row["reward"]),
                )
            )
            action_rows.append(
                (
                    int(session_id),
                    int(row["tick"]),
                    int(row["action_id"]),
                    1 if bool(row["valid"]) else 0,
                )
            )

        if tick_rows:
            self.conn.executemany(
                """
                INSERT INTO game_ticks (session_id, tick, state_json, reward)
                VALUES (?, ?, ?, ?)
                """,
                tick_rows,
            )
        if action_rows:
            self.conn.executemany(
                """
                INSERT INTO actions (session_id, tick, action_id, valid)
                VALUES (?, ?, ?, ?)
                """,
                action_rows,
            )
        self.conn.commit()

    def record_session(
        self,
        session_id: int,
        result: str,
        score: int,
        survived_time: float,
        rows: Iterable[dict[str, Any]],
    ) -> None:
        self.write_step_logs(session_id, rows)
        self.finalize_session(session_id, result, score, survived_time)

    def close(self) -> None:
        self.conn.close()
