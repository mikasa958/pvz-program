from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass, field
from typing import Any

from config import GameConfig


@dataclass(frozen=True)
class WaveModifier:
    id: str
    name: str
    description: str
    enemy_speed_multiplier: float = 1.0
    enemy_hp_multiplier: float = 1.0
    enemy_count_multiplier: float = 1.0
    spawn_interval_multiplier: float = 1.0
    lane_mode: str = "spread"
    target_row: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enemy_speed_multiplier": round(float(self.enemy_speed_multiplier), 4),
            "enemy_hp_multiplier": round(float(self.enemy_hp_multiplier), 4),
            "enemy_count_multiplier": round(float(self.enemy_count_multiplier), 4),
            "spawn_interval_multiplier": round(float(self.spawn_interval_multiplier), 4),
            "lane_mode": self.lane_mode,
        }
        if self.target_row is not None:
            payload["target_row"] = int(self.target_row)
        return payload


def _steady_modifier() -> WaveModifier:
    return WaveModifier(
        id="steady",
        name="Steady Push",
        description="Baseline wave with no extra modifier.",
        enemy_speed_multiplier=1.0,
        enemy_hp_multiplier=1.0,
        enemy_count_multiplier=1.0,
        spawn_interval_multiplier=1.0,
        lane_mode="spread",
    )


@dataclass(frozen=True)
class WaveSpawn:
    delay: float
    row: int
    enemy_type_id: str = "normal"
    spawn_at: float | None = None

    def __post_init__(self) -> None:
        if self.spawn_at is None:
            object.__setattr__(self, "spawn_at", float(self.delay))

    def to_dict(self) -> dict[str, Any]:
        return {
            "delay": round(float(self.delay), 4),
            "spawn_at": round(float(self.spawn_at or 0.0), 4),
            "row": int(self.row),
            "enemy_type_id": str(self.enemy_type_id),
        }


@dataclass(frozen=True)
class EnemySpawnSpec:
    enemy_type_id: str


@dataclass
class WaveConfig:
    wave_id: int
    fixed_counts: dict[str, int] = field(default_factory=dict)
    random_slots: int = 0
    actual_total_range: tuple[int, int] = (0, 0)
    first_spawn_delay: float = 0.0
    last_spawn_target: float = 0.0
    checkpoint_upgrade: bool = True
    start_requires_clear_field: bool = False
    spawn_interval: float = 0.0
    modifier: WaveModifier = field(default_factory=_steady_modifier)
    spawns: list[WaveSpawn] = field(default_factory=list)
    preview_rows: list[int] = field(default_factory=list)
    notes: str = ""

    @property
    def index(self) -> int:
        return int(self.wave_id)

    @property
    def enemy_count(self) -> int:
        return len(self.spawns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wave_id": int(self.wave_id),
            "index": int(self.wave_id),
            "fixed_counts": copy.deepcopy(self.fixed_counts),
            "random_slots": int(self.random_slots),
            "actual_total_range": [int(self.actual_total_range[0]), int(self.actual_total_range[1])],
            "actual_total": int(self.enemy_count),
            "enemy_count": int(self.enemy_count),
            "first_spawn_delay": round(float(self.first_spawn_delay), 4),
            "last_spawn_target": round(float(self.last_spawn_target), 4),
            "checkpoint_upgrade": bool(self.checkpoint_upgrade),
            "start_requires_clear_field": bool(self.start_requires_clear_field),
            "spawn_interval": round(float(self.spawn_interval), 4),
            "modifier": self.modifier.to_dict(),
            "preview_rows": [int(row) for row in self.preview_rows],
            "spawns": [spawn.to_dict() for spawn in self.spawns],
            "notes": self.notes,
        }


CAMPAIGN_V5_WAVE_SPECS: list[WaveConfig] = [
    WaveConfig(1, {"normal": 2}, 0, (2, 2), 6.01, 28.0, False),
    WaveConfig(2, {"normal": 1, "pole_vaulting": 1}, 0, (2, 2), 6.01, 28.0, False),
    WaveConfig(3, {}, 4, (4, 4), 6.01, 28.0, False),
    WaveConfig(4, {}, 5, (3, 5), 6.01, 28.0, True),
    WaveConfig(5, {}, 6, (4, 6), 6.01, 28.0, False),
    WaveConfig(6, {"normal": 3}, 6, (7, 9), 6.01, 28.0, False),
    WaveConfig(7, {"normal": 4}, 7, (9, 11), 6.01, 28.0, True),
    WaveConfig(
        8,
        {"normal": 8},
        8,
        (14, 16),
        6.01,
        28.0,
        False,
        start_requires_clear_field=True,
        notes="清场后刷新 w9",
    ),
    WaveConfig(9, {"normal": 8, "pole_vaulting": 4}, 8, (18, 20), 6.01, 31.0, False),
    WaveConfig(10, {}, 16, (14, 16), 6.01, 28.0, True),
    WaveConfig(11, {}, 16, (14, 16), 6.01, 28.0, False),
    WaveConfig(12, {"normal": 8}, 10, (15, 18), 6.01, 28.0, False),
    WaveConfig(13, {}, 18, (15, 18), 6.01, 28.0, True),
    WaveConfig(
        14,
        {"normal": 10},
        10,
        (18, 20),
        6.01,
        31.0,
        False,
        start_requires_clear_field=True,
        notes="清场后刷新 w15",
    ),
    WaveConfig(15, {"buckethead": 15, "pole_vaulting": 12, "normal": 8}, 0, (35, 35), 6.01, 31.0, False),
]


CAMPAIGN_V4_WAVE_SPECS: list[WaveConfig] = [
    WaveConfig(1, {"normal": 1}, 0, (1, 1), 0.0, 15.0, False, notes="first global spawn at 10s after grace"),
    WaveConfig(2, {"normal": 1}, 0, (1, 1), 6.01, 25.0, False),
    WaveConfig(3, {"normal": 1}, 0, (1, 1), 6.01, 25.0, False),
    WaveConfig(4, {}, 2, (1, 2), 6.01, 25.0, True),
    WaveConfig(5, {}, 2, (1, 2), 6.01, 25.0, False),
    WaveConfig(6, {}, 2, (1, 2), 6.01, 25.0, False),
    WaveConfig(7, {"normal": 1}, 2, (2, 3), 6.01, 25.0, False),
    WaveConfig(8, {"normal": 1}, 2, (2, 3), 6.01, 25.0, True),
    WaveConfig(9, {"normal": 3}, 4, (5, 7), 6.01, 28.0, False),
    WaveConfig(10, {"normal": 5, "pole_vaulting": 2}, 6, (10, 12), 6.01, 31.0, False),
    WaveConfig(11, {}, 6, (2, 4), 6.01, 28.0, False),
    WaveConfig(12, {}, 6, (3, 6), 6.01, 28.0, True),
    WaveConfig(13, {"normal": 2}, 6, (5, 8), 6.01, 28.0, False),
    WaveConfig(14, {"normal": 2}, 6, (5, 8), 6.01, 28.0, False),
    WaveConfig(15, {"normal": 2}, 6, (5, 8), 6.01, 28.0, False),
    WaveConfig(16, {}, 8, (5, 8), 6.01, 28.0, True),
    WaveConfig(17, {}, 8, (5, 8), 6.01, 28.0, False),
    WaveConfig(18, {}, 8, (5, 8), 6.01, 28.0, False),
    WaveConfig(19, {"normal": 5}, 8, (11, 13), 6.01, 31.0, True),
    WaveConfig(20, {"normal": 12, "pole_vaulting": 7, "buckethead": 6}, 0, (25, 25), 6.01, 31.0, False),
]


class LaneBalancer:
    """Assign spawn lanes and times with per-wave randomness and lane-count balance."""

    _MIN_SPAWN_GAP_SECONDS = 0.35
    _MAX_STREAK_SAME_LANE = 2

    def __init__(self, config: GameConfig, rng: random.Random) -> None:
        self.config = config
        self.random = rng
        self.row_count = int(config.grid_rows)
        self.threat_weights = {
            str(enemy_type): float(weight) for enemy_type, weight in config.lane_threat_weights.items()
        }
        self.spawn_count: list[int] = [0 for _ in range(self.row_count)]
        self.threat_score: list[float] = [0.0 for _ in range(self.row_count)]
        self.assigned_rows: list[int] = []

    def assign_rows(self, enemy_types: list[str], wave_id: int) -> list[int]:
        del wave_id  # kept for API compatibility with older callers
        self.spawn_count = [0 for _ in range(self.row_count)]
        self.threat_score = [0.0 for _ in range(self.row_count)]
        lane_slots = self._build_balanced_lane_slots(len(enemy_types))
        self.assigned_rows = self._match_types_to_lane_slots(enemy_types, lane_slots)
        for row, enemy_type in zip(self.assigned_rows, enemy_types):
            self.spawn_count[row] += 1
            self.threat_score[row] += self._threat_weight(enemy_type)
        return list(self.assigned_rows)

    def _match_types_to_lane_slots(self, enemy_types: list[str], lane_slots: list[int]) -> list[int]:
        if not enemy_types:
            return []
        remaining_slots = list(lane_slots)
        threat_by_row = [0.0 for _ in range(self.row_count)]
        assignments = [0 for _ in range(len(enemy_types))]
        spawn_order = sorted(
            range(len(enemy_types)),
            key=lambda index: (self._threat_weight(enemy_types[index]), self.random.random()),
            reverse=True,
        )
        for index in spawn_order:
            enemy_type = enemy_types[index]
            threat_weight = self._threat_weight(enemy_type)
            slot_index = min(
                range(len(remaining_slots)),
                key=lambda candidate: (
                    threat_by_row[remaining_slots[candidate]] + threat_weight,
                    remaining_slots[candidate],
                    self.random.random(),
                ),
            )
            row = remaining_slots.pop(slot_index)
            assignments[index] = row
            threat_by_row[row] += threat_weight
        return assignments

    def assign_spawn_times(self, spawn_count: int, first_delay: float, last_target: float) -> list[float]:
        if spawn_count <= 0:
            return []
        start = float(first_delay)
        end = float(last_target)
        if spawn_count == 1:
            return [start]

        window = max(0.0, end - start)
        if window <= 0.0:
            return [start for _ in range(spawn_count)]

        min_gap = min(self._MIN_SPAWN_GAP_SECONDS, window / max(1, spawn_count - 1))
        best_times: list[float] | None = None
        best_score = -1.0
        for _ in range(8):
            candidate = self._sample_stratified_spawn_times(spawn_count, start, end, min_gap)
            candidate[0] = start
            for index in range(1, len(candidate)):
                if candidate[index] < candidate[index - 1] + min_gap:
                    candidate[index] = min(end, candidate[index - 1] + min_gap)
            if candidate[-1] > end:
                overflow = candidate[-1] - end
                candidate = [max(start, value - overflow) for value in candidate]
            score = self._spawn_time_randomness_score(candidate)
            if score > best_score:
                best_score = score
                best_times = candidate
        return best_times if best_times is not None else self._sample_stratified_spawn_times(spawn_count, start, end, min_gap)

    def _build_balanced_lane_slots(self, spawn_count: int) -> list[int]:
        if spawn_count <= 0:
            return []
        if spawn_count <= self.row_count:
            return self.random.sample(list(range(self.row_count)), spawn_count)

        base, remainder = divmod(spawn_count, self.row_count)
        quotas = [base for _ in range(self.row_count)]
        for row in self.random.sample(list(range(self.row_count)), remainder):
            quotas[row] += 1

        slots: list[int] = []
        for row, quota in enumerate(quotas):
            slots.extend([row] * int(quota))
        self.random.shuffle(slots)
        return self._reduce_lane_streaks(slots, self._MAX_STREAK_SAME_LANE)

    def _sample_stratified_spawn_times(
        self,
        spawn_count: int,
        start: float,
        end: float,
        min_gap: float,
    ) -> list[float]:
        window = end - start
        segment = window / float(spawn_count)
        times: list[float] = []
        for index in range(spawn_count):
            seg_start = start + segment * index
            seg_end = start + segment * (index + 1)
            if index == spawn_count - 1:
                seg_end = end
            if seg_end <= seg_start:
                times.append(seg_start)
            else:
                times.append(self.random.uniform(seg_start, seg_end))
        times.sort()
        for index in range(1, len(times)):
            if times[index] - times[index - 1] < min_gap:
                times[index] = min(end, times[index - 1] + min_gap)
        if times[-1] > end:
            overflow = times[-1] - end
            times = [max(start, value - overflow) for value in times]
            for index in range(1, len(times)):
                if times[index] - times[index - 1] < min_gap:
                    times[index] = min(end, times[index - 1] + min_gap)
        times[0] = max(start, times[0])
        times[-1] = min(end, times[-1])
        return times

    @staticmethod
    def _spawn_time_randomness_score(times: list[float]) -> float:
        if len(times) < 2:
            return 1.0
        gaps = [times[index + 1] - times[index] for index in range(len(times) - 1)]
        if not gaps:
            return 1.0
        mean_gap = sum(gaps) / len(gaps)
        if mean_gap <= 1e-6:
            return 0.0
        variance = sum((gap - mean_gap) ** 2 for gap in gaps) / len(gaps)
        return variance / (mean_gap * mean_gap)

    def _reduce_lane_streaks(self, rows: list[int], max_streak: int) -> list[int]:
        if max_streak < 1 or len(rows) <= max_streak:
            return rows
        slots = list(rows)
        for _ in range(len(slots) * 4):
            streak_row: int | None = None
            streak_len = 0
            for row in slots:
                if row == streak_row:
                    streak_len += 1
                else:
                    streak_row = row
                    streak_len = 1
                if streak_len > max_streak:
                    swap_index = self._find_swap_index(slots, row)
                    if swap_index is None:
                        break
                    slots[swap_index], slots[-1] = slots[-1], slots[swap_index]
                    break
            else:
                return slots
        return slots

    def _find_swap_index(self, slots: list[int], streak_row: int) -> int | None:
        candidates = [index for index, row in enumerate(slots) if row != streak_row]
        if not candidates:
            return None
        return int(self.random.choice(candidates))

    def snapshot(self, alive_enemy_count: list[int] | None = None) -> list[dict[str, Any]]:
        alive = alive_enemy_count or [0 for _ in range(self.row_count)]
        payload: list[dict[str, Any]] = []
        for row in range(self.row_count):
            payload.append(
                {
                    "row": row,
                    "spawn_count": int(self.spawn_count[row]),
                    "threat_score": round(float(self.threat_score[row]), 2),
                    "alive_enemy_count": int(alive[row]) if row < len(alive) else 0,
                }
            )
        return payload

    def _threat_weight(self, enemy_type: str) -> float:
        return float(self.threat_weights.get(enemy_type, self.threat_weights.get("normal", 1.0)))


class WaveManager:
    def __init__(self, config: GameConfig) -> None:
        self.config = config
        self.random = random.Random()
        self.lane_balancer = LaneBalancer(config, self.random)
        self.waves: list[WaveConfig] = []
        self.current_wave: WaveConfig | None = None
        self.current_wave_index = -1
        self.pending_spawns: list[WaveSpawn] = []
        self.time_until_next_spawn = 0.0
        self.wave_elapsed = 0.0
        self.active = False

    @property
    def total_waves(self) -> int:
        return len(self.waves)

    def reset(self, seed: int) -> None:
        self.random.seed(seed)
        self.waves = self._build_waves()
        self.current_wave = None
        self.current_wave_index = -1
        self.pending_spawns = []
        self.time_until_next_spawn = 0.0
        self.wave_elapsed = 0.0
        self.active = False
        self.lane_balancer.spawn_count = [0 for _ in range(self.config.grid_rows)]
        self.lane_balancer.threat_score = [0.0 for _ in range(self.config.grid_rows)]
        self.lane_balancer.assigned_rows = []

    def start_next_wave(self) -> WaveConfig | None:
        next_index = self.current_wave_index + 1
        if next_index >= len(self.waves):
            self.current_wave = None
            self.pending_spawns = []
            self.time_until_next_spawn = 0.0
            self.wave_elapsed = 0.0
            self.active = False
            return None

        self.current_wave_index = next_index
        self.current_wave = copy.deepcopy(self.waves[next_index])
        self.pending_spawns = sorted(copy.deepcopy(self.current_wave.spawns), key=lambda spawn: float(spawn.spawn_at or 0.0))
        self.time_until_next_spawn = float(self.pending_spawns[0].spawn_at) if self.pending_spawns else 0.0
        self.wave_elapsed = 0.0
        self.active = True
        return self.current_wave

    def update(self, dt: float) -> None:
        if not self.active:
            self.time_until_next_spawn = 0.0
            return
        self.wave_elapsed += max(0.0, float(dt))
        if self.pending_spawns:
            self.time_until_next_spawn = max(0.0, float(self.pending_spawns[0].spawn_at or 0.0) - self.wave_elapsed)
        else:
            self.time_until_next_spawn = 0.0

    def should_spawn(self) -> bool:
        if not self.active or not self.pending_spawns:
            return False
        next_spawn = self.pending_spawns[0]
        return float(next_spawn.spawn_at or 0.0) <= self.wave_elapsed + 1e-9

    def get_next_spawn(self) -> WaveSpawn | None:
        if not self.should_spawn():
            return None
        spawn = self.pending_spawns.pop(0)
        if self.pending_spawns:
            self.time_until_next_spawn = max(0.0, float(self.pending_spawns[0].spawn_at or 0.0) - self.wave_elapsed)
        else:
            self.time_until_next_spawn = 0.0
        return spawn

    def remaining_spawns(self) -> int:
        return len(self.pending_spawns)

    def cancel_pending_spawns(self) -> None:
        self.pending_spawns = []
        self.time_until_next_spawn = 0.0

    def prime_spawns_for_immediate_start(self, first_delay: float = 0.0) -> None:
        """Shift spawn schedule so the first zombie appears after first_delay seconds."""
        if not self.pending_spawns:
            self.wave_elapsed = 0.0
            self.time_until_next_spawn = 0.0
            return

        lead_in = max(0.0, float(first_delay))
        first_spawn_at = float(self.pending_spawns[0].spawn_at or 0.0)
        offset = first_spawn_at - lead_in
        reprimed: list[WaveSpawn] = []
        for spawn in self.pending_spawns:
            spawn_at = max(lead_in, float(spawn.spawn_at or 0.0) - offset)
            reprimed.append(
                WaveSpawn(
                    delay=spawn_at,
                    spawn_at=spawn_at,
                    row=int(spawn.row),
                    enemy_type_id=str(spawn.enemy_type_id),
                )
            )
        self.pending_spawns = sorted(reprimed, key=lambda spawn: float(spawn.spawn_at or 0.0))
        self.wave_elapsed = 0.0
        self.time_until_next_spawn = lead_in

    def finish_current_wave(self) -> None:
        self.pending_spawns = []
        self.current_wave = None
        self.time_until_next_spawn = 0.0
        self.wave_elapsed = 0.0
        self.active = False

    def is_wave_active(self) -> bool:
        return self.active

    def is_wave_cleared(self, enemies: list[Any]) -> bool:
        if self.current_wave is None:
            return False
        return not self.pending_spawns and not enemies

    def are_spawns_complete(self) -> bool:
        return self.active and not self.pending_spawns

    def lane_pressure_snapshot(self, enemies: list[Any]) -> list[dict[str, Any]]:
        alive_counts = [0 for _ in range(self.config.grid_rows)]
        for enemy in enemies:
            row = int(getattr(enemy, "row", -1))
            if 0 <= row < len(alive_counts):
                alive_counts[row] += 1
        return self.lane_balancer.snapshot(alive_counts)

    def _build_waves(self) -> list[WaveConfig]:
        plan_id = str(self.config.wave_plan_id)
        if plan_id == "campaign_v5":
            return self._build_campaign_v5_waves()
        if plan_id == "campaign_v4":
            return self._build_campaign_v4_waves()
        return self._build_legacy_random_waves()

    def _build_legacy_random_waves(self) -> list[WaveConfig]:
        waves: list[WaveConfig] = []
        modifier_ids = [key for key in self.config.wave_modifier_pool.keys() if key != "steady"]
        for wave_id in range(1, int(self.config.total_waves) + 1):
            base_enemy_count = int(self.config.wave_base_enemy_count) + (wave_id - 1) * int(self.config.wave_enemy_count_step)
            modifier_id = self.random.choice(modifier_ids) if modifier_ids else "steady"
            modifier = self._modifier_from_pool(modifier_id)
            if modifier.id == "single_lane":
                modifier = WaveModifier(
                    **{
                        **modifier.to_dict(),
                        "target_row": self.random.randrange(self.config.grid_rows),
                    }
                )

            enemy_count = max(1, int(math.ceil(base_enemy_count * float(modifier.enemy_count_multiplier))))
            base_interval = max(
                0.4,
                float(self.config.enemy_spawn_interval) - (wave_id - 1) * float(self.config.wave_spawn_interval_decay),
            )
            spawn_interval = max(0.25, base_interval * float(modifier.spawn_interval_multiplier))

            if modifier.lane_mode == "single_lane" and modifier.target_row is not None:
                rows = [int(modifier.target_row) for _ in range(enemy_count)]
            else:
                rows = [self.random.randrange(self.config.grid_rows) for _ in range(enemy_count)]
            spawns = [
                WaveSpawn(
                    delay=spawn_interval * index,
                    spawn_at=spawn_interval * index,
                    row=row,
                    enemy_type_id="normal",
                )
                for index, row in enumerate(rows)
            ]
            waves.append(
                WaveConfig(
                    wave_id=wave_id,
                    fixed_counts={"normal": enemy_count},
                    random_slots=0,
                    actual_total_range=(enemy_count, enemy_count),
                    first_spawn_delay=0.0,
                    last_spawn_target=spawn_interval * max(0, enemy_count - 1),
                    checkpoint_upgrade=True,
                    spawn_interval=spawn_interval,
                    modifier=modifier,
                    spawns=spawns,
                    preview_rows=list(rows),
                )
            )
        return waves

    def _build_campaign_v5_waves(self) -> list[WaveConfig]:
        return self._build_campaign_waves_from_specs(CAMPAIGN_V5_WAVE_SPECS)

    def _build_campaign_v4_waves(self) -> list[WaveConfig]:
        return self._build_campaign_waves_from_specs(CAMPAIGN_V4_WAVE_SPECS)

    def _build_campaign_waves_from_specs(self, specs: list[WaveConfig]) -> list[WaveConfig]:
        waves: list[WaveConfig] = []
        for base_wave in specs:
            wave = copy.deepcopy(base_wave)
            wave.modifier = _steady_modifier()

            spawn_types = self._campaign_spawn_types(wave)
            rows = self.lane_balancer.assign_rows(spawn_types, wave.wave_id)
            last_target = float(wave.last_spawn_target)
            first_delay = float(wave.first_spawn_delay)
            spawn_times = self.lane_balancer.assign_spawn_times(len(spawn_types), first_delay, last_target)
            spawn_entries = sorted(
                zip(spawn_times, rows, spawn_types),
                key=lambda item: float(item[0]),
            )
            ordered_rows = [int(row) for _, row, _ in spawn_entries]
            ordered_rows = self.lane_balancer._reduce_lane_streaks(
                ordered_rows,
                self.lane_balancer._MAX_STREAK_SAME_LANE,
            )
            spawn_entries = [
                (spawn_at, ordered_rows[index], enemy_type_id)
                for index, (spawn_at, _, enemy_type_id) in enumerate(spawn_entries)
            ]
            if len(spawn_entries) > 1:
                gaps = [
                    float(spawn_entries[index + 1][0]) - float(spawn_entries[index][0])
                    for index in range(len(spawn_entries) - 1)
                ]
                wave.spawn_interval = sum(gaps) / len(gaps)
            else:
                wave.spawn_interval = 0.0
            wave.spawns = [
                WaveSpawn(
                    delay=float(spawn_at),
                    spawn_at=float(spawn_at),
                    row=int(row),
                    enemy_type_id=str(enemy_type_id),
                )
                for spawn_at, row, enemy_type_id in spawn_entries
            ]
            wave.preview_rows = [int(row) for _, row, _ in spawn_entries]
            waves.append(wave)
        return waves

    def _campaign_spawn_types(self, wave: WaveConfig) -> list[str]:
        fixed_list: list[str] = []
        if wave.wave_id == 20:
            fixed_list.extend(["buckethead"] * int(wave.fixed_counts.get("buckethead", 0)))
            fixed_list.extend(["pole_vaulting"] * int(wave.fixed_counts.get("pole_vaulting", 0)))
            fixed_list.extend(["normal"] * int(wave.fixed_counts.get("normal", 0)))
        else:
            for enemy_type, count in wave.fixed_counts.items():
                fixed_list.extend([str(enemy_type)] * int(count))

        actual_min, actual_max = wave.actual_total_range
        actual_total = self.random.randint(int(actual_min), int(actual_max))
        random_count = max(0, min(int(wave.random_slots), actual_total - len(fixed_list)))
        random_list = [self._campaign_random_enemy_type(wave.wave_id) for _ in range(random_count)]
        combined = fixed_list + random_list
        self.random.shuffle(combined)
        return combined

    def _campaign_random_enemy_type(self, wave_id: int) -> str:
        if 4 <= int(wave_id) <= 9:
            return str(self.random.choices(["normal", "pole_vaulting"], weights=[40, 60], k=1)[0])
        return str(self.random.choices(["normal", "pole_vaulting", "buckethead"], weights=[25, 45, 30], k=1)[0])

    def _modifier_from_pool(self, modifier_id: str) -> WaveModifier:
        payload = dict(self.config.wave_modifier_pool.get(modifier_id, self.config.wave_modifier_pool["steady"]))
        return WaveModifier(
            id=str(modifier_id),
            name=str(payload.get("name", modifier_id)),
            description=str(payload.get("description", "")),
            enemy_speed_multiplier=float(payload.get("enemy_speed_multiplier", 1.0)),
            enemy_hp_multiplier=float(payload.get("enemy_hp_multiplier", 1.0)),
            enemy_count_multiplier=float(payload.get("enemy_count_multiplier", 1.0)),
            spawn_interval_multiplier=float(payload.get("spawn_interval_multiplier", 1.0)),
            lane_mode=str(payload.get("lane_mode", "spread")),
            target_row=None,
        )


def build_wave_manager(config: GameConfig) -> WaveManager:
    return WaveManager(config)
