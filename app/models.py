from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class RawRow:
    line_no: int
    raw: str
    cells: List[str]


@dataclass
class RawEvent:
    line_no: int
    raw: str
    cells: List[str]
    name: str
    timestamp: Optional[datetime]
    values: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_no": self.line_no,
            "name": self.name,
            "timestamp": iso(self.timestamp),
            "values": self.values,
            "raw": self.raw,
        }


@dataclass
class Phase:
    phase_id: str
    label: str
    start_at: Optional[datetime]
    end_at: Optional[datetime]
    duration_sec: Optional[int]
    source_start_line: Optional[int]
    source_end_line: Optional[int]
    confidence: str = "exact"
    group: str = "unclassified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "label": self.label,
            "start_at": iso(self.start_at),
            "end_at": iso(self.end_at),
            "duration_sec": self.duration_sec,
            "source_start_line": self.source_start_line,
            "source_end_line": self.source_end_line,
            "confidence": self.confidence,
            "group": self.group,
        }


@dataclass
class BoardAttempt:
    attempt_id: str
    board_no: Optional[int] = None
    board_number: Optional[int] = None
    shift_board_no: Optional[int] = None
    attempt_no: int = 1
    column: Optional[int] = None
    row: Optional[int] = None
    take_start: Optional[datetime] = None
    take_end: Optional[datetime] = None
    set_start: Optional[datetime] = None
    prepare_start: Optional[datetime] = None
    insert_start: Optional[datetime] = None
    set_end: Optional[datetime] = None
    insert_motion: Optional[str] = None
    attach_motion: Optional[str] = None
    status: str = "UNKNOWN"
    force_sensor_branch: Optional[str] = None
    force_sensor_at: Optional[datetime] = None
    force_sensor_line: Optional[int] = None
    need_remove_board: bool = False
    need_remove_at: Optional[datetime] = None
    need_remove_line: Optional[int] = None
    manual_stop: bool = False
    manual_stop_line: Optional[int] = None
    source_start_line: Optional[int] = None
    source_end_line: Optional[int] = None
    warnings: List[str] = field(default_factory=list)

    def duration_between(self, start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
        if start is None or end is None:
            return None
        seconds = int((end - start).total_seconds())
        return seconds if seconds >= 0 else None

    def take_duration_sec(self) -> Optional[int]:
        return self.duration_between(self.take_start, self.take_end)

    def install_duration_sec(self) -> Optional[int]:
        return self.duration_between(self.insert_start, self.set_end)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "board_no": self.board_no,
            "board_number": self.board_number,
            "shift_board_no": self.shift_board_no,
            "attempt_no": self.attempt_no,
            "column": self.column,
            "row": self.row,
            "take_start": iso(self.take_start),
            "take_end": iso(self.take_end),
            "set_start": iso(self.set_start),
            "prepare_start": iso(self.prepare_start),
            "insert_start": iso(self.insert_start),
            "set_end": iso(self.set_end),
            "insert_motion": self.insert_motion,
            "attach_motion": self.attach_motion,
            "status": self.status,
            "force_sensor_branch": self.force_sensor_branch,
            "force_sensor_at": iso(self.force_sensor_at),
            "need_remove_board": self.need_remove_board,
            "need_remove_at": iso(self.need_remove_at),
            "manual_stop": self.manual_stop,
            "take_duration_sec": self.take_duration_sec(),
            "install_duration_sec": self.install_duration_sec(),
            "source_start_line": self.source_start_line,
            "source_end_line": self.source_end_line,
            "warnings": self.warnings,
        }


@dataclass
class AreaCycle:
    area_id: str
    session_no: int
    area_seq: int
    column: Optional[int] = None
    row: Optional[int] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    move_start_at: Optional[datetime] = None
    move_start_line: Optional[int] = None
    move_confidence: str = "inferred"
    centering_values: List[Dict[str, Any]] = field(default_factory=list)
    area_obstacle: Optional[List[bool]] = None
    board_skip: Dict[int, bool] = field(default_factory=dict)
    scans: Dict[str, Any] = field(default_factory=dict)
    board_scan: Dict[int, List[bool]] = field(default_factory=dict)
    board_motion: Dict[int, Dict[str, Optional[str]]] = field(default_factory=dict)
    area_completed: Optional[List[bool]] = None
    board_attempts: List[BoardAttempt] = field(default_factory=list)
    phases: List[Phase] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_start_line: Optional[int] = None
    source_end_line: Optional[int] = None
    raw_events: List[RawEvent] = field(default_factory=list)

    def duration_sec(self) -> Optional[int]:
        if self.start_at is None or self.end_at is None:
            return None
        seconds = int((self.end_at - self.start_at).total_seconds())
        return seconds if seconds >= 0 else None

    def total_phase_duration_sec(self) -> int:
        return sum(phase.duration_sec or 0 for phase in self.phases)

    def to_dict(self, detail: bool = False) -> Dict[str, Any]:
        payload = {
            "area_id": self.area_id,
            "session_no": self.session_no,
            "area_seq": self.area_seq,
            "column": self.column,
            "row": self.row,
            "start_at": iso(self.start_at),
            "end_at": iso(self.end_at),
            "duration_sec": self.duration_sec(),
            "centering_values": self.centering_values,
            "area_obstacle": self.area_obstacle,
            "board_skip": {str(k): v for k, v in self.board_skip.items()},
            "board_scan": {str(k): v for k, v in self.board_scan.items()},
            "board_motion": {str(k): v for k, v in self.board_motion.items()},
            "area_completed": self.area_completed,
            "board_attempts": [attempt.to_dict() for attempt in self.board_attempts],
            "phases": [phase.to_dict() for phase in self.phases],
            "warnings": self.warnings,
            "source_start_line": self.source_start_line,
            "source_end_line": self.source_end_line,
        }
        if detail:
            payload["raw_events"] = [event.to_dict() for event in self.raw_events]
            payload["scans"] = self.scans
        return payload


@dataclass
class Session:
    session_no: int
    start_at: Optional[datetime]
    end_at: Optional[datetime] = None
    columns: int = 3
    rows: int = 5
    board_loaded: Optional[int] = None
    areas: List[AreaCycle] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_start_line: Optional[int] = None
    source_end_line: Optional[int] = None

    def duration_sec(self) -> Optional[int]:
        if self.start_at is None or self.end_at is None:
            return None
        seconds = int((self.end_at - self.start_at).total_seconds())
        return seconds if seconds >= 0 else None

    def to_dict(self, detail: bool = False) -> Dict[str, Any]:
        return {
            "session_no": self.session_no,
            "start_at": iso(self.start_at),
            "end_at": iso(self.end_at),
            "duration_sec": self.duration_sec(),
            "columns": self.columns,
            "rows": self.rows,
            "board_loaded": self.board_loaded,
            "area_count": len(self.areas),
            "areas": [area.to_dict(detail=detail) for area in self.areas],
            "warnings": self.warnings,
            "source_start_line": self.source_start_line,
            "source_end_line": self.source_end_line,
        }


@dataclass
class AnalysisResult:
    file_name: str
    parsed_at: datetime
    sessions: List[Session]
    event_count: int
    warnings: List[str] = field(default_factory=list)
    source_path: Optional[str] = None
    event_name_counts: Dict[str, int] = field(default_factory=dict)
    force_branch_counts: Dict[str, int] = field(default_factory=dict)
    need_remove_count: int = 0

    def to_dict(self, detail: bool = False) -> Dict[str, Any]:
        return {
            "file_name": self.file_name,
            "parsed_at": iso(self.parsed_at),
            "sessions": [session.to_dict(detail=detail) for session in self.sessions],
            "event_count": self.event_count,
            "warnings": self.warnings,
            "source_path": self.source_path,
            "event_name_counts": self.event_name_counts,
            "force_branch_counts": self.force_branch_counts,
            "need_remove_count": self.need_remove_count,
        }
