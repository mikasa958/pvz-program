from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import sys
from typing import Any


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _map_effect_summary(state: dict[str, Any]) -> dict[str, int]:
    summary: dict[str, int] = {}
    map_effects = state.get("map_effects", [])
    if not isinstance(map_effects, list):
        return summary

    for item in map_effects:
        if not isinstance(item, dict):
            continue
        effect = item.get("effect", {})
        if not isinstance(effect, dict):
            continue
        effect_id = str(effect.get("id", "unknown"))
        summary[effect_id] = summary.get(effect_id, 0) + 1

    if summary:
        summary["total"] = len(map_effects)
    return summary


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
    wave_id: int | None = None
    wave_state: str | None = None
    wave_modifier: str = "{}"
    active_upgrades: str = "[]"
    pending_upgrade_options: str = "[]"
    modifiers: str = "{}"
    selected_plant: str | None = None
    valid_actions_count: int | None = None
    map_effect_summary: str = "{}"


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
        self.output_dir = Path(output_dir) if output_dir is not None else _runtime_base_dir() / "logs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[TickRecord] = []
        self.session_summary: dict[str, Any] = {}

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

        state_payload = dict(state or {})
        state_json = _compact_json(state_payload)
        wave_modifier_payload = state_payload.get("wave_modifier", state_payload.get("current_wave_modifier", {}))
        active_upgrades_payload = state_payload.get("active_upgrades", [])
        pending_upgrade_payload = state_payload.get("pending_upgrade_options", [])
        modifiers_payload = state_payload.get("modifiers", {})
        valid_actions_count = state_payload.get("valid_actions_count")
        map_effect_summary = _map_effect_summary(state_payload)

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
                wave_id=int(state_payload["wave_id"]) if state_payload.get("wave_id") is not None else None,
                wave_state=str(state_payload["wave_state"]) if state_payload.get("wave_state") is not None else None,
                wave_modifier=_compact_json(wave_modifier_payload or {}),
                active_upgrades=_compact_json(active_upgrades_payload or []),
                pending_upgrade_options=_compact_json(pending_upgrade_payload or []),
                modifiers=_compact_json(modifiers_payload or {}),
                selected_plant=str(state_payload["selected_plant"]) if state_payload.get("selected_plant") is not None else None,
                valid_actions_count=int(valid_actions_count) if valid_actions_count is not None else None,
                map_effect_summary=_compact_json(map_effect_summary),
            )
        )

    def build_session_summary(
        self,
        *,
        result: str,
        state: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        state_payload = dict(state or {})
        summary = {
            "result": result,
            "victory": bool(state_payload.get("victory", False)),
            "final_wave": int(state_payload.get("wave_id", 0)),
            "total_kills": int(state_payload.get("kills", 0)),
            "final_score": int(state_payload.get("score", 0)),
            "selected_upgrades": list(state_payload.get("active_upgrades", [])),
            "seed": int(seed) if seed is not None else None,
        }
        return summary

    def set_session_summary(self, summary: dict[str, Any] | None) -> None:
        self.session_summary = dict(summary or {})

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
            "wave_id",
            "wave_state",
            "wave_modifier",
            "active_upgrades",
            "pending_upgrade_options",
            "modifiers",
            "selected_plant",
            "valid_actions_count",
            "map_effect_summary",
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
            "summary": self.session_summary,
            "records": self.to_rows(),
        }
        with target.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return target
