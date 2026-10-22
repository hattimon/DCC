"""Persistent, opt-in schedules with explicit time zones and restart handoff."""

from __future__ import annotations

import calendar
import copy
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_CONFIG = {
    "enabled": False, "action": "scan", "panel_first": False,
    "kind": "daily", "time": "03:00", "date": "", "timezone": "UTC",
    "weekday": 0, "month_day": 1, "every": 1, "unit": "days", "targets": [],
}


def validate_config(payload: dict, now: float | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Nieprawidłowe ustawienia harmonogramu.")
    config = {key: copy.deepcopy(payload.get(key, value)) for key, value in DEFAULT_CONFIG.items()}
    if any(not isinstance(config[key], bool) for key in ("enabled", "panel_first")):
        raise ValueError("Przełączniki harmonogramu muszą mieć wartość true albo false.")
    if (not isinstance(config["kind"], str) or not isinstance(config["action"], str)
            or config["kind"] not in {"once", "daily", "weekly", "monthly", "interval"} or config["action"] not in {"scan", "update"}):
        raise ValueError("Nieprawidłowy rodzaj harmonogramu lub operacji.")
    if not isinstance(config["time"], str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", config["time"]):
        raise ValueError("Podaj prawidłową godzinę HH:MM.")
    if not isinstance(config["timezone"], str) or len(config["timezone"]) > 100:
        raise ValueError("Nieprawidłowa strefa czasowa.")
    try:
        ZoneInfo(config["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Nieznana strefa czasowa. Użyj nazwy IANA, np. Europe/Warsaw.") from None
    for key, minimum, maximum in (("weekday", 0, 6), ("month_day", 1, 31), ("every", 1, 8760)):
        if type(config[key]) is not int or not minimum <= config[key] <= maximum:
            raise ValueError("Nieprawidłowy odstęp lub dzień harmonogramu.")
    if not isinstance(config["unit"], str) or config["unit"] not in {"hours", "days"}:
        raise ValueError("Nieprawidłowa jednostka odstępu harmonogramu.")
    if config["kind"] in {"once", "interval"}:
        try:
            date.fromisoformat(config["date"])
        except (ValueError, TypeError):
            raise ValueError("Wybierz datę rozpoczęcia harmonogramu.") from None
    targets = config["targets"]
    if not isinstance(targets, list) or len(targets) > 100:
        raise ValueError("Harmonogram może zawierać najwyżej 100 wybranych kontenerów.")
    cleaned = {}
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Nieprawidłowa lista kontenerów harmonogramu.")
        name, repository = target.get("name"), target.get("repository")
        if (not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name)
                or not isinstance(repository, str) or not repository or len(repository) > 400
                or any(char.isspace() for char in repository)):
            raise ValueError("Nieprawidłowa lista kontenerów harmonogramu.")
        cleaned[name] = {"name": name, "repository": repository}
    config["targets"] = list(cleaned.values())
    if config["enabled"] and config["action"] == "update" and not config["targets"]:
        raise ValueError("Wybierz kontenery do aktualizacji w harmonogramie.")
    if config["enabled"] and config["kind"] == "once" and next_run(config, time.time() if now is None else now) is None:
        raise ValueError("Termin jednorazowego harmonogramu musi być w przyszłości.")
    return config


def _wall_time(day: date, clock: str, zone: ZoneInfo) -> float:
    hour, minute = map(int, clock.split(":"))
    # First occurrence during a repeated hour; a missing spring-forward time
    # moves forward by the DST gap. The persisted due time prevents duplicates.
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone, fold=0).timestamp()


def next_run(config: dict, after: float) -> float | None:
    if not config["enabled"]:
        return None
    zone = ZoneInfo(config["timezone"])
    local = datetime.fromtimestamp(after, zone)
    kind, clock = config["kind"], config["time"]
    if kind == "once":
        candidate = _wall_time(date.fromisoformat(config["date"]), clock, zone)
        return candidate if candidate > after else None
    if kind == "interval":
        anchor = date.fromisoformat(config["date"])
        start = _wall_time(anchor, clock, zone)
        if config["unit"] == "hours":
            seconds = config["every"] * 3600
            count = max(0, math.floor((after - start) / seconds) + 1)
            return start + count * seconds
        count = max(0, (local.date() - anchor).days // config["every"])
        candidate = _wall_time(anchor + timedelta(days=count * config["every"]), clock, zone)
        return candidate if candidate > after else _wall_time(anchor + timedelta(days=(count + 1) * config["every"]), clock, zone)
    if kind in {"daily", "weekly"}:
        day = local.date()
        if kind == "weekly":
            day += timedelta(days=(config["weekday"] - day.weekday()) % 7)
        candidate = _wall_time(day, clock, zone)
        return candidate if candidate > after else _wall_time(day + timedelta(days=7 if kind == "weekly" else 1), clock, zone)
    # Day 29/30/31 is clamped to the last day of a shorter month.
    year, month = local.year, local.month
    for _ in range(2):
        day = min(config["month_day"], calendar.monthrange(year, month)[1])
        candidate = _wall_time(date(year, month, day), clock, zone)
        if candidate > after:
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    raise ValueError("Nie można wyznaczyć następnego terminu harmonogramu.")


class ScheduleStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.state = {"config": copy.deepcopy(DEFAULT_CONFIG), "next_run": None, "pending": None, "last_run": None}
        self.corrupt = False
        try:
            if path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(saved, dict) or not isinstance(saved.get("config"), dict) or not isinstance(saved["config"].get("enabled"), bool):
                    raise ValueError("Invalid schedule state")
                config = validate_config({**saved["config"], "enabled": False})
                config["enabled"] = saved["config"].get("enabled") is True
                due = saved.get("next_run")
                if due is not None and (type(due) not in {int, float} or not math.isfinite(due)):
                    raise ValueError("Invalid due time")
                pending = saved.get("pending")
                if pending is not None:
                    if not isinstance(pending, dict) or not isinstance(pending.get("config"), dict):
                        raise ValueError("Invalid pending run")
                    checked = validate_config({**pending["config"], "enabled": False})
                    if (pending.get("phase") not in ("running", "awaiting_restart", "containers")
                            or not isinstance(pending.get("instance"), str)
                            or type(pending.get("started_at")) not in {int, float} or not math.isfinite(pending["started_at"])
                            or (checked["action"] == "update" and not checked["targets"])):
                        raise ValueError("Invalid pending phase")
                    if pending["phase"] == "awaiting_restart" and (
                            not isinstance(pending.get("expected_image"), str)
                            or not re.fullmatch(r"sha256:[0-9a-f]{64}", pending["expected_image"])
                            or type(pending.get("deadline")) not in {int, float} or not math.isfinite(pending["deadline"])):
                        raise ValueError("Invalid restart handoff")
                last = saved.get("last_run")
                if last is not None and (not isinstance(last, dict) or last.get("status") not in ("success", "error")
                        or not isinstance(last.get("message"), str) or type(last.get("finished_at")) not in {int, float}
                        or not math.isfinite(last["finished_at"])):
                    raise ValueError("Invalid last result")
                self.state.update(config=config, next_run=due, pending=pending, last_run=saved.get("last_run"))
        except (OSError, ValueError, TypeError, KeyError):
            self.corrupt = True  # Never execute or silently overwrite damaged schedule state.

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)

    def snapshot(self) -> dict:
        with self.lock:
            return {**copy.deepcopy(self.state), "storage_error": self.corrupt, "configured": self.path.exists()}

    def save(self, config: dict, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        config = validate_config(config, now)
        with self.lock:
            if self.corrupt:
                raise ValueError("Plik harmonogramu jest uszkodzony; zachowano go do ręcznego sprawdzenia.")
            if self.state["pending"]:
                raise ValueError("Harmonogram jest w trakcie wykonania. Poczekaj na zakończenie.")
            previous = copy.deepcopy(self.state)
            self.state.update(config=config, next_run=next_run(config, now))
            try:
                self._write()
            except OSError:
                self.state = previous
                raise
            return self.snapshot()

    def due(self, instance: str, now: float) -> bool:
        with self.lock:
            if self.corrupt:
                return False
            pending = self.state["pending"]
            if pending:
                return pending.get("instance") != instance or (
                    pending["phase"] == "awaiting_restart" and now >= pending.get("deadline", 0))
            return bool(self.state["config"]["enabled"] and self.state["next_run"] is not None and self.state["next_run"] <= now)

    def claim(self, instance: str, now: float) -> dict | None:
        with self.lock:
            if self.state["pending"] or not self.due(instance, now):
                return None
            config = copy.deepcopy(self.state["config"])
            previous = copy.deepcopy(self.state)
            pending = {"id": secrets.token_urlsafe(12), "config": config, "phase": "running", "instance": instance, "started_at": now}
            self.state["pending"] = pending
            self.state["next_run"] = next_run(config, now)
            if config["kind"] == "once":
                self.state["config"]["enabled"] = False
            try:
                self._write()  # Claim durably before any Docker mutation.
            except OSError:
                self.state = previous
                raise
            return copy.deepcopy(pending)

    def phase(self, phase: str, instance: str, **values) -> None:
        with self.lock:
            self.state["pending"].update(phase=phase, instance=instance, **values)
            self._write()

    def finish(self, status: str, message: str, now: float | None = None) -> None:
        with self.lock:
            self.state["last_run"] = {"status": status, "message": message, "finished_at": time.time() if now is None else now}
            self.state["pending"] = None
            self._write()
