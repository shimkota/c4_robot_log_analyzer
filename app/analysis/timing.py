from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from app.models import AreaCycle, BoardAttempt, Phase, RawEvent


PHASE_DEFINITIONS = {
    "move": ("移動", "move"),
    "centering": ("車体位置調整", "centering"),
    "il_scan_x": ("IL Xスキャン", "scan"),
    "d405_up": ("D405上スキャン", "scan"),
    "il_scan_y": ("IL Yスキャン", "scan"),
    "il_scan_z": ("IL Zスキャン", "scan"),
    "obstacle_capture": ("障害物画像取得", "scan"),
    "pattern_calc": ("障害物計算・選択", "calc"),
    "take_board": ("ボード取得", "take"),
    "pre_insert": ("取り付け前処理", "install"),
    "install": ("取り付け", "install"),
    "force_reverse": ("逆再生", "reverse"),
    "force_release": ("置く", "place"),
    "manual_wait": ("手動対応", "manual"),
}


def _duration(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
    if start is None or end is None:
        return None
    seconds = int((end - start).total_seconds())
    return seconds if seconds >= 0 else None


def _events(area: AreaCycle, name: str) -> List[RawEvent]:
    return [event for event in area.raw_events if event.name == name]


def _first(area: AreaCycle, name: str) -> Optional[RawEvent]:
    events = _events(area, name)
    return events[0] if events else None


def _last(area: AreaCycle, name: str) -> Optional[RawEvent]:
    events = _events(area, name)
    return events[-1] if events else None


def _add_phase(
    phases: List[Phase],
    phase_id: str,
    label: str,
    start: Optional[datetime],
    end: Optional[datetime],
    start_line: Optional[int],
    end_line: Optional[int],
    confidence: str = "exact",
    group: str = "unclassified",
) -> None:
    if start is None and end is None:
        return
    duration = _duration(start, end)
    if start is not None and end is not None and duration is None:
        confidence = "incomplete"
    phases.append(
        Phase(
            phase_id=phase_id,
            label=label,
            start_at=start,
            end_at=end,
            duration_sec=duration,
            source_start_line=start_line,
            source_end_line=end_line,
            confidence=confidence if duration is not None else "incomplete",
            group=group,
        )
    )


def _definition(phase_id: str) -> tuple[str, str]:
    return PHASE_DEFINITIONS.get(phase_id, (phase_id, "unclassified"))


def _board_label(board_no: Optional[int], base_label: str, attempt_no: int) -> str:
    board = f"B{board_no}" if board_no else "B?"
    if attempt_no > 1:
        return f"{board} {base_label} #{attempt_no}"
    return f"{board} {base_label}"


def _attempt_phase(
    phases: List[Phase],
    attempt: BoardAttempt,
    phase_id: str,
    start: Optional[datetime],
    end: Optional[datetime],
    start_line: Optional[int],
    end_line: Optional[int],
    confidence: str = "exact",
) -> None:
    label, group = _definition(phase_id)
    suffix = attempt.attempt_id.replace(":", "_")
    _add_phase(
        phases,
        f"{phase_id}_{suffix}",
        _board_label(attempt.board_no, label, attempt.attempt_no),
        start,
        end,
        start_line,
        end_line,
        confidence=confidence,
        group=group,
    )


def _attempt_start_time(attempt: BoardAttempt) -> Optional[datetime]:
    return attempt.take_start or attempt.set_start or attempt.prepare_start or attempt.insert_start


def _next_attempt_after(
    attempts: List[BoardAttempt],
    index: int,
    line_no: Optional[int],
) -> Optional[BoardAttempt]:
    for candidate in attempts[index + 1 :]:
        if line_no is None or candidate.source_start_line is None or candidate.source_start_line > line_no:
            return candidate
    return None


def _post_cancel_end(
    area: AreaCycle,
    attempts: List[BoardAttempt],
    index: int,
    attempt: BoardAttempt,
) -> tuple[Optional[datetime], Optional[int], str]:
    next_attempt = _next_attempt_after(attempts, index, attempt.force_sensor_line or attempt.need_remove_line)
    if next_attempt is not None:
        return _attempt_start_time(next_attempt), next_attempt.source_start_line, "exact"
    return area.end_at, area.source_end_line, "inferred"


def analyze_area_timing(area: AreaCycle) -> None:
    phases: List[Phase] = []
    centering_start = _first(area, "CenteringStart")
    centering_end = _first(area, "CenteringEnd")

    if area.move_start_at is not None and centering_start is not None:
        label, group = _definition("move")
        _add_phase(
            phases,
            f"move_{area.area_id}",
            label,
            area.move_start_at,
            centering_start.timestamp,
            area.move_start_line,
            centering_start.line_no,
            confidence=area.move_confidence,
            group=group,
        )

    label, group = _definition("centering")
    _add_phase(
        phases,
        f"centering_{area.area_id}",
        label,
        centering_start.timestamp if centering_start else None,
        centering_end.timestamp if centering_end else None,
        centering_start.line_no if centering_start else None,
        centering_end.line_no if centering_end else None,
        group=group,
    )

    scan_pairs = [
        ("il_scan_x", _first(area, "ILScanStart"), _first(area, "ILScanXEnd")),
        ("d405_up", _first(area, "ILScanXEnd"), _first(area, "D405UpScanEnd")),
        ("il_scan_y", _first(area, "D405UpScanEnd"), _first(area, "ILScanYEnd")),
        ("il_scan_z", _first(area, "ILScanYEnd"), _first(area, "ILScanZEnd")),
        ("obstacle_capture", _first(area, "ObstacleScanStart"), _last(area, "CamGetDataEnd")),
        ("pattern_calc", _first(area, "ObstacleCalcStart"), _first(area, "ObstacleCalcEndCheck")),
    ]
    for phase_id, start_event, end_event in scan_pairs:
        label, group = _definition(phase_id)
        _add_phase(
            phases,
            f"{phase_id}_{area.area_id}",
            label,
            start_event.timestamp if start_event else None,
            end_event.timestamp if end_event else None,
            start_event.line_no if start_event else None,
            end_event.line_no if end_event else None,
            group=group,
        )

    attempts = list(area.board_attempts)
    for index, attempt in enumerate(attempts):
        _attempt_phase(
            phases,
            attempt,
            "take_board",
            attempt.take_start,
            attempt.take_end,
            attempt.source_start_line,
            attempt.source_start_line,
        )
        _attempt_phase(
            phases,
            attempt,
            "pre_insert",
            attempt.set_start,
            attempt.insert_start,
            attempt.source_start_line,
            attempt.source_start_line,
        )
        install_end = attempt.set_end or attempt.force_sensor_at
        _attempt_phase(
            phases,
            attempt,
            "install",
            attempt.insert_start,
            install_end,
            attempt.source_start_line,
            attempt.source_end_line or attempt.force_sensor_line,
        )
        if attempt.force_sensor_branch == "ReverseAction" or attempt.need_remove_board:
            end_at, end_line, confidence = _post_cancel_end(area, attempts, index, attempt)
            _attempt_phase(
                phases,
                attempt,
                "force_reverse",
                attempt.force_sensor_at or attempt.need_remove_at,
                end_at,
                attempt.force_sensor_line or attempt.need_remove_line,
                end_line,
                confidence=confidence,
            )
        elif attempt.force_sensor_branch == "BoardRelease":
            end_at, end_line, confidence = _post_cancel_end(area, attempts, index, attempt)
            _attempt_phase(
                phases,
                attempt,
                "force_release",
                attempt.force_sensor_at,
                end_at,
                attempt.force_sensor_line,
                end_line,
                confidence=confidence,
            )

    phases.sort(key=lambda phase: (phase.source_start_line or 0, phase.phase_id))
    area.phases = phases


def analyze_timings(areas: Iterable[AreaCycle]) -> None:
    for area in areas:
        analyze_area_timing(area)
