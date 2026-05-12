from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TickRecord:
    tick: int
    time: float
    resources: int
    base_hp: int
    action_id: int
    reward: float
    done: bool
    valid: bool
    state_json: str


class GameLogger:
    """Collect per-step logs for one game session."""

    def __init__(
        self,
        mode: str,
        session_id: int | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.mode = mode
        self.session_id = session_id
        self.created_at = datetime.now()
        self.output_dir = Path(output_dir) if output_dir is not None else Path(__file__).resolve().parent / "logs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[TickRecord] = []

    def log_step(
        self,
        tick: int,
        time: float,
        resources: int,
        base_hp: int,
        action_id: int,
        reward: float,
        done: bool,
        valid: bool,
        state: dict[str, Any] | None = None,
    ) -> None:
        if self.session_id is None:
            return
        state_json = json.dumps(state or {}, ensure_ascii=False, default=str, separators=(",", ":"))
        self.records.append(
            TickRecord(
                tick=int(tick),
                time=float(time),
                resources=int(resources),
                base_hp=int(base_hp),
                action_id=int(action_id),
                reward=float(reward),
                done=bool(done),
                valid=bool(valid),
                state_json=state_json,
            )
        )

    def to_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in self.records:
            row = asdict(record)
            row["session_id"] = self.session_id
            row["mode"] = self.mode
            row["created_at"] = self.created_at.isoformat(timespec="seconds")
            rows.append(row)
        return rows

    def default_stem(self) -> str:
        timestamp = self.created_at.strftime("%Y%m%d_%H%M%S")
        session_part = f"{self.session_id:06d}" if self.session_id is not None else "pending"
        return f"session_{session_part}_{self.mode}_{timestamp}"

    def save_csv(self, path: str | Path | None = None) -> Path:
        if self.session_id is None:
            return self.output_dir / "skipped.csv"
        target = Path(path) if path is not None else self.output_dir / f"{self.default_stem()}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)

        rows = self.to_rows()
        fieldnames = [
            "session_id",
            "mode",
            "created_at",
            "tick",
            "time",
            "resources",
            "base_hp",
            "action_id",
            "reward",
            "done",
            "valid",
            "state_json",
        ]
        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return target

    def save_json(self, path: str | Path | None = None) -> Path:
        if self.session_id is None:
            return self.output_dir / "skipped.json"
        target = Path(path) if path is not None else self.output_dir / f"{self.default_stem()}.json"
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "session_id": self.session_id,
            "mode": self.mode,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "records": self.to_rows(),
        }
        with target.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return target
