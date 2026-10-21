from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import sys
from typing import Any, Iterable


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class GameDatabase:
    """SQLite storage for session summaries, per-tick state and actions."""

    SESSION_EXTRA_COLUMNS: dict[str, str] = {
        "victory": "INTEGER",
        "final_wave": "INTEGER",
        "total_kills": "INTEGER",
        "final_score": "INTEGER",
        "selected_upgrades": "TEXT",
        "seed": "INTEGER",
    }
    TICK_EXTRA_COLUMNS: dict[str, str] = {
        "wave_id": "INTEGER",
        "wave_state": "TEXT",
        "wave_modifier": "TEXT",
        "active_upgrades": "TEXT",
        "pending_upgrade_options": "TEXT",
        "modifiers": "TEXT",
        "selected_plant": "TEXT",
        "valid_actions_count": "INTEGER",
        "map_effect_summary": "TEXT",
    }

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _runtime_base_dir() / "logs" / "game_log.sqlite3"
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
                survived_time REAL NOT NULL,
                victory INTEGER,
                final_wave INTEGER,
                total_kills INTEGER,
                final_score INTEGER,
                selected_upgrades TEXT,
                seed INTEGER
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
                wave_id INTEGER,
                wave_state TEXT,
                wave_modifier TEXT,
                active_upgrades TEXT,
                pending_upgrade_options TEXT,
                modifiers TEXT,
                selected_plant TEXT,
                valid_actions_count INTEGER,
                map_effect_summary TEXT,
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
        self._ensure_columns("game_sessions", self.SESSION_EXTRA_COLUMNS)
        self._ensure_columns("game_ticks", self.TICK_EXTRA_COLUMNS)
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

    def _ensure_columns(self, table_name: str, columns: dict[str, str]) -> None:
        existing_columns = self._table_columns(table_name)
        for column_name, column_type in columns.items():
            if column_name in existing_columns:
                continue
            self.conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def _table_columns(self, table_name: str) -> set[str]:
        rows = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row[1]) for row in rows}

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
        session_summary: dict[str, Any] | None = None,
    ) -> None:
        summary = dict(session_summary or {})
        victory_value = None if "victory" not in summary else (1 if bool(summary.get("victory")) else 0)
        final_wave = int(summary["final_wave"]) if summary.get("final_wave") is not None else None
        total_kills = int(summary["total_kills"]) if summary.get("total_kills") is not None else None
        final_score = int(summary["final_score"]) if summary.get("final_score") is not None else None
        selected_upgrades = _compact_json(summary.get("selected_upgrades", []))
        seed = int(summary["seed"]) if summary.get("seed") is not None else None

        self.conn.execute(
            """
            UPDATE game_sessions
            SET result = ?,
                score = ?,
                survived_time = ?,
                victory = ?,
                final_wave = ?,
                total_kills = ?,
                final_score = ?,
                selected_upgrades = ?,
                seed = ?
            WHERE id = ?
            """,
            (
                result,
                int(score),
                float(survived_time),
                victory_value,
                final_wave,
                total_kills,
                final_score,
                selected_upgrades,
                seed,
                int(session_id),
            ),
        )
        self.conn.commit()

    def write_step_logs(self, session_id: int, rows: Iterable[dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return

        tick_rows: list[tuple[Any, ...]] = []
        action_rows: list[tuple[int, int, int, int]] = []

        for row in rows:
            tick_rows.append(
                (
                    int(session_id),
                    int(row["tick"]),
                    str(row["state_json"]),
                    float(row["reward"]),
                    int(row["wave_id"]) if row.get("wave_id") is not None else None,
                    row.get("wave_state"),
                    str(row.get("wave_modifier", "{}")),
                    str(row.get("active_upgrades", "[]")),
                    str(row.get("pending_upgrade_options", "[]")),
                    str(row.get("modifiers", "{}")),
                    row.get("selected_plant"),
                    int(row["valid_actions_count"]) if row.get("valid_actions_count") is not None else None,
                    str(row.get("map_effect_summary", "{}")),
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
                INSERT INTO game_ticks (
                    session_id,
                    tick,
                    state_json,
                    reward,
                    wave_id,
                    wave_state,
                    wave_modifier,
                    active_upgrades,
                    pending_upgrade_options,
                    modifiers,
                    selected_plant,
                    valid_actions_count,
                    map_effect_summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        session_summary: dict[str, Any] | None = None,
    ) -> None:
        self.write_step_logs(session_id, rows)
        self.finalize_session(session_id, result, score, survived_time, session_summary=session_summary)

    def close(self) -> None:
        self.conn.close()
