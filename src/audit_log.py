import json
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable

from src.exceptions import InvalidOperationError


class AuditLog:
    """Keep events in memory and append the same JSON records to a file."""

    def __init__(self, file_path: str | Path, clock: Callable[[], datetime] | None = None):
        self.file_path = Path(file_path)
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)
        self.records: list[dict] = []

    @staticmethod
    def _json_value(value):
        if isinstance(value, dict):
            return {
                key: AuditLog._json_value(item)
                for key, item in value.items() if "password" not in str(key).lower()
            }
        if isinstance(value, (list, tuple)):
            return [AuditLog._json_value(item) for item in value]
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        return value

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise InvalidOperationError("Audit time must include a timezone")
        return value.astimezone(timezone.utc)

    def record(
        self,
        level: str,
        event: str,
        message: str,
        *,
        client_id: str | None = None,
        transaction_id: str | None = None,
        details: dict | None = None,
        timestamp: datetime | None = None,
    ) -> dict:
        if level not in ("INFO", "WARNING", "ERROR"):
            raise InvalidOperationError("Invalid audit level")
        now = self._utc(timestamp if timestamp is not None else self.clock())
        entry = {
            "timestamp": now.isoformat(),
            "level": level,
            "event": event,
            "client_id": client_id,
            "transaction_id": transaction_id,
            "message": message,
            "details": self._json_value(details if details is not None else {}),
        }
        line = json.dumps(entry, ensure_ascii=False, allow_nan=False)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("a", encoding="utf-8") as output:
            output.write(line + "\n")
        self.records.append(entry)
        return deepcopy(entry)

    def filter(
        self,
        level: str | None = None,
        client_id: str | None = None,
        event: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[dict]:
        if date_from is not None:
            date_from = self._utc(date_from)
        if date_to is not None:
            date_to = self._utc(date_to)
        result = []
        for entry in self.records:
            if level is not None and entry["level"] != level:
                continue
            if client_id is not None and entry["client_id"] != client_id:
                continue
            if event is not None and entry["event"] != event:
                continue
            timestamp = datetime.fromisoformat(entry["timestamp"])
            if date_from is not None and timestamp < date_from:
                continue
            if date_to is not None and timestamp > date_to:
                continue
            result.append(deepcopy(entry))
        return result

    def get_suspicious_operations(self) -> list[dict]:
        return [
            entry for entry in self.filter(event="risk_analyzed")
            if entry["details"].get("risk_level") in ("MEDIUM", "HIGH")
        ]

    def get_error_statistics(self) -> dict[str, int]:
        return dict(Counter(
            entry["details"].get("error_type", "UnknownError")
            for entry in self.records if entry["level"] == "ERROR"
        ))
