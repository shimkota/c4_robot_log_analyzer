from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable, List, Optional

from app.models import RawEvent, RawRow

TIMESTAMP_RE = re.compile(r"^\d{8}_\d{2}:\d{2}:\d{2}_\d{4}$")


def parse_timestamp(value: str) -> Optional[datetime]:
    text = value.strip()
    if not TIMESTAMP_RE.match(text):
        return None
    # The trailing ffff field is deliberately ignored. Everything is second precision.
    return datetime.strptime(text[:17], "%Y%m%d_%H:%M:%S")


def normalize_name(first_cell: str) -> tuple[str, List[str]]:
    first = first_cell.strip()
    if ":" in first:
        name, tail = first.split(":", 1)
        tail = tail.strip()
        return name.strip(), [tail] if tail else []
    return first, []


def parse_event(row: RawRow) -> RawEvent:
    cells = [cell.strip() for cell in row.cells]
    first = cells[0] if cells else ""
    name, embedded_values = normalize_name(first)
    remaining = cells[1:]
    timestamp = None
    if remaining:
        parsed = parse_timestamp(remaining[0])
        if parsed is not None:
            timestamp = parsed
            remaining = remaining[1:]
    values = [value for value in embedded_values + remaining if value != ""]
    return RawEvent(
        line_no=row.line_no,
        raw=row.raw,
        cells=cells,
        name=name,
        timestamp=timestamp,
        values=values,
    )


def parse_events(rows: Iterable[RawRow]) -> List[RawEvent]:
    return [parse_event(row) for row in rows]


def parse_bool(value: str) -> Optional[bool]:
    token = value.strip().strip("[]").strip()
    lowered = token.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def parse_bool_list(values: Iterable[str]) -> List[bool]:
    text = ",".join(values).replace("[", "").replace("]", "")
    parsed: List[bool] = []
    for part in text.split(","):
        value = parse_bool(part)
        if value is not None:
            parsed.append(value)
    return parsed


def parse_int(values: Iterable[str]) -> Optional[int]:
    for value in values:
        text = value.strip().strip("[]")
        if text == "":
            continue
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def parse_float(values: Iterable[str]) -> Optional[float]:
    for value in values:
        text = value.strip().strip("[]")
        if text == "":
            continue
        try:
            return float(text)
        except ValueError:
            return None
    return None

