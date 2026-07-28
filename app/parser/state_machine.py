from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import re
from typing import List, Optional

from app.analysis.status import classify_area
from app.analysis.timing import analyze_timings
from app.models import AnalysisResult, AreaCycle, BoardAttempt, RawEvent, Session
from app.parser.event_parser import parse_bool, parse_bool_list, parse_events, parse_float, parse_int
from app.parser.raw_reader import read_raw_rows


RELATIVE_MOVE_EVENTS = {"RelativeMoveFBStart", "RelativeMoveLRStart"}
COMPLETION_MARKERS = {"ScanCompletedEnd", "AreaCompleted"}
BOARD_SHIFT_PATTERN = re.compile(r"^Board([1-4])_(?:381Shift|LastShift)$")
FORWARD_INSTALL_BOARD_ORDER = (4, 1, 3, 2)
BACKWARD_INSTALL_BOARD_ORDER = (1, 4, 2, 3)


def _movement_delta(left: AreaCycle, right: AreaCycle, axis: str) -> Optional[int]:
    if (
        left.column is None
        or left.row is None
        or right.column is None
        or right.row is None
    ):
        return None
    if axis == "row" and left.column == right.column and left.row != right.row:
        return right.row - left.row
    if axis == "column" and left.row == right.row and left.column != right.column:
        return right.column - left.column
    return None


def _session_travel_basis(areas: List[AreaCycle]) -> tuple[str, int]:
    row_moves = 0
    column_moves = 0
    for left, right in zip(areas, areas[1:]):
        row_delta = _movement_delta(left, right, "row")
        column_delta = _movement_delta(left, right, "column")
        if row_delta is not None:
            row_moves += 1
        if column_delta is not None:
            column_moves += 1

    axis = "row" if row_moves >= column_moves else "column"
    for left, right in zip(areas, areas[1:]):
        delta = _movement_delta(left, right, axis)
        if delta is not None:
            return axis, 1 if delta > 0 else -1
    return axis, 1


def _area_travel_direction(
    areas: List[AreaCycle],
    index: int,
    axis: str,
    forward_sign: int,
) -> str:
    current = areas[index]
    if index + 1 < len(areas):
        next_delta = _movement_delta(current, areas[index + 1], axis)
        if next_delta is not None:
            return "forward" if next_delta * forward_sign > 0 else "backward"
    if index > 0:
        previous_delta = _movement_delta(areas[index - 1], current, axis)
        if previous_delta is not None:
            return "forward" if previous_delta * forward_sign > 0 else "backward"
    return "forward"


def parse_log_file(path: Path) -> AnalysisResult:
    rows = read_raw_rows(path)
    events = parse_events(rows)
    return build_analysis(events, file_name=path.name, source_path=str(path))


def build_analysis(
    events: List[RawEvent],
    file_name: str = "memory.csv",
    source_path: Optional[str] = None,
) -> AnalysisResult:
    sessions: List[Session] = []
    warnings: List[str] = []
    current_session: Optional[Session] = None
    current_area: Optional[AreaCycle] = None
    current_attempt: Optional[BoardAttempt] = None
    last_closed_attempt: Optional[BoardAttempt] = None
    previous_area_end_event: Optional[RawEvent] = None
    pending_move_events: List[RawEvent] = []
    pending_il_scan_board: Optional[int] = None
    last_event: Optional[RawEvent] = None
    last_timestamp_event: Optional[RawEvent] = None

    def start_session(event: RawEvent) -> None:
        nonlocal current_session, previous_area_end_event
        session_no = len(sessions) + 1
        current_session = Session(
            session_no=session_no,
            start_at=event.timestamp,
            source_start_line=event.line_no,
        )
        sessions.append(current_session)
        previous_area_end_event = None
        pending_move_events.clear()

    def area_has_completion_marker(area: AreaCycle) -> bool:
        return any(event.name in COMPLETION_MARKERS for event in area.raw_events)

    def close_area(reason: Optional[str] = None, end_event: Optional[RawEvent] = None) -> None:
        nonlocal current_area, current_attempt, last_closed_attempt, previous_area_end_event
        if current_area is None:
            return
        source_event = end_event or last_event
        if source_event is not None:
            current_area.end_at = current_area.end_at or source_event.timestamp
            current_area.source_end_line = current_area.source_end_line or source_event.line_no
            if source_event.timestamp is not None:
                previous_area_end_event = source_event
            else:
                timed_events = [event for event in current_area.raw_events if event.timestamp is not None]
                previous_area_end_event = timed_events[-1] if timed_events else source_event
        if reason:
            current_area.warnings.append(reason)
        current_attempt = None
        last_closed_attempt = None
        current_area = None

    def start_area(event: RawEvent, move_event: Optional[RawEvent] = None) -> AreaCycle:
        nonlocal current_area
        assert current_session is not None
        area_seq = len(current_session.areas) + 1
        move_start_at = None
        move_start_line = None
        move_confidence = "inferred"
        source_start_line = event.line_no
        start_at = event.timestamp
        if move_event is not None:
            move_start_at = move_event.timestamp
            move_start_line = move_event.line_no
            move_confidence = "exact"
            start_at = move_event.timestamp or event.timestamp
            source_start_line = move_event.line_no
        elif previous_area_end_event is not None and previous_area_end_event.timestamp is not None:
            move_start_at = previous_area_end_event.timestamp
            move_start_line = previous_area_end_event.line_no
            start_at = previous_area_end_event.timestamp
            move_confidence = "inferred"
            source_start_line = previous_area_end_event.line_no
        current_area = AreaCycle(
            area_id=f"S{current_session.session_no}-A{area_seq}",
            session_no=current_session.session_no,
            area_seq=area_seq,
            start_at=start_at,
            move_start_at=move_start_at,
            move_start_line=move_start_line,
            move_confidence=move_confidence,
            source_start_line=source_start_line,
        )
        current_session.areas.append(current_area)
        return current_area

    def append_to_area(event: RawEvent) -> None:
        if current_area is not None:
            current_area.raw_events.append(event)

    def last_centering_sample() -> Optional[dict]:
        if current_area is None or not current_area.centering_values:
            return None
        return current_area.centering_values[-1]

    def append_centering_sample(event: RawEvent) -> None:
        if current_area is None:
            return
        current_area.centering_values.append(
            {
                "line_no": event.line_no,
                "at": event.timestamp.strftime("%Y-%m-%d %H:%M:%S") if event.timestamp else None,
                "x": None,
                "y": None,
                "z": None,
                "gamma": None,
                "area_obstacle": None,
            }
        )

    def ensure_attempt(event: RawEvent) -> Optional[BoardAttempt]:
        nonlocal current_attempt, last_closed_attempt
        if current_session is None or current_area is None:
            return None
        if current_attempt is None or current_attempt.set_end is not None:
            current_attempt = BoardAttempt(
                attempt_id=f"S{current_session.session_no}-A{current_area.area_seq}-L{event.line_no}",
                source_start_line=event.line_no,
            )
            current_area.board_attempts.append(current_attempt)
            last_closed_attempt = None
        return current_attempt

    def active_or_last_attempt() -> Optional[BoardAttempt]:
        if current_attempt is not None:
            return current_attempt
        if current_area is None or not current_area.board_attempts:
            return None
        unfinished = [attempt for attempt in current_area.board_attempts if attempt.set_end is None]
        if unfinished:
            return unfinished[-1]
        return current_area.board_attempts[-1]

    def apply_area_coordinate(attempt: BoardAttempt, field: str, value: Optional[int], event: RawEvent) -> None:
        if current_area is None or value is None:
            return
        setattr(attempt, field, value)
        existing = getattr(current_area, field)
        if existing is None:
            setattr(current_area, field, value)
        elif existing != value:
            current_area.warnings.append(
                f"{field} mismatch at line {event.line_no}: area={existing}, board={value}"
            )

    def set_attempt_board_no(attempt: BoardAttempt, board_no: Optional[int]) -> None:
        if current_area is None or board_no is None:
            return
        attempt.board_no = board_no
        previous = [
            other
            for other in current_area.board_attempts
            if other is not attempt and other.board_no == board_no
        ]
        attempt.attempt_no = len(previous) + 1
        motion = current_area.board_motion.get(board_no, {})
        attempt.insert_motion = motion.get("insert")
        attempt.attach_motion = motion.get("attach")

    def board_shift_no(event: RawEvent) -> Optional[int]:
        match = BOARD_SHIFT_PATTERN.match(event.name)
        return int(match.group(1)) if match else None

    def resolve_area_attempt_numbers(area: AreaCycle) -> None:
        counts: Counter[int] = Counter()
        for attempt in area.board_attempts:
            if attempt.board_no is None:
                continue
            counts[attempt.board_no] += 1
            attempt.attempt_no = counts[attempt.board_no]
            motion = area.board_motion.get(attempt.board_no, {})
            attempt.insert_motion = motion.get("insert")
            attempt.attach_motion = motion.get("attach")

    def is_pass_motion(area: AreaCycle, board_no: int) -> bool:
        motion = area.board_motion.get(board_no, {})
        return motion.get("insert") == "E" and motion.get("attach") == "E"

    def has_motion(area: AreaCycle, board_no: int) -> bool:
        motion = area.board_motion.get(board_no, {})
        return bool(motion.get("insert") or motion.get("attach"))

    def planned_board_numbers(area: AreaCycle, install_order: tuple[int, ...]) -> List[int]:
        return [
            board_no
            for board_no in install_order
            if area.board_skip.get(board_no) is not True
            and has_motion(area, board_no)
            and not is_pass_motion(area, board_no)
        ]

    def resolve_board_numbers() -> None:
        for session in sessions:
            axis, forward_sign = _session_travel_basis(session.areas)
            for area_index, area in enumerate(session.areas):
                travel_direction = _area_travel_direction(session.areas, area_index, axis, forward_sign)
                install_order = (
                    FORWARD_INSTALL_BOARD_ORDER
                    if travel_direction == "forward"
                    else BACKWARD_INSTALL_BOARD_ORDER
                )
                target_board_numbers = planned_board_numbers(area, install_order)
                for index, attempt in enumerate(area.board_attempts):
                    attempt.board_no = None
                    resolved_board_no = (
                        target_board_numbers[index]
                        if index < len(target_board_numbers)
                        else attempt.shift_board_no
                    )
                    if resolved_board_no is not None:
                        attempt.board_no = resolved_board_no
                resolve_area_attempt_numbers(area)

    def update_session_metadata(event: RawEvent) -> None:
        if current_session is None:
            return
        if event.name == "Columns":
            value = parse_int(event.values)
            if value is not None:
                current_session.columns = value
        elif event.name == "Rows":
            value = parse_int(event.values)
            if value is not None:
                current_session.rows = value
        elif event.name == "BoardLoaded":
            current_session.board_loaded = parse_int(event.values)

    for event in events:
        if event.name == "AutoStart":
            if current_session is not None:
                close_area("AutoStart encountered before AreaCompleted", end_event=last_event)
                if last_timestamp_event is not None:
                    current_session.end_at = last_timestamp_event.timestamp
                    current_session.source_end_line = last_timestamp_event.line_no
            start_session(event)
            last_timestamp_event = event if event.timestamp is not None else last_timestamp_event
            last_event = event
            continue

        if current_session is None:
            if event.timestamp is not None:
                last_timestamp_event = event
            last_event = event
            continue

        update_session_metadata(event)

        if event.name in RELATIVE_MOVE_EVENTS:
            if current_area is not None:
                close_area("New movement started before AreaCompleted", end_event=last_event)
            pending_move_events.append(event)
            if event.timestamp is not None:
                last_timestamp_event = event
            last_event = event
            continue

        if event.name == "CenteringStart":
            if current_area is not None and area_has_completion_marker(current_area):
                close_area("AreaCompleted missing; closed at next CenteringStart", end_event=last_event)
            if current_area is None:
                move_event = pending_move_events[0] if pending_move_events else None
                start_area(event, move_event=move_event)
                if current_area is not None and pending_move_events:
                    current_area.raw_events.extend(pending_move_events)
                pending_move_events.clear()
            append_to_area(event)
            append_centering_sample(event)
            if event.timestamp is not None:
                last_timestamp_event = event
            last_event = event
            continue

        append_to_area(event)

        if pending_il_scan_board is not None and current_area is not None and event.name == "x":
            current_area.scans[f"board{pending_il_scan_board}_il_raw"] = event.cells
            pending_il_scan_board = None

        if event.name in {"X", "Y", "Z", "Gamma"}:
            sample = last_centering_sample()
            if sample is not None:
                sample[event.name.lower()] = parse_float(event.values)
        elif event.name == "AreaOblstacle":
            values = parse_bool_list(event.values)
            if current_area is not None:
                current_area.area_obstacle = values
                sample = last_centering_sample()
                if sample is not None:
                    sample["area_obstacle"] = values
        elif event.name.startswith("Board") and event.name.endswith("Skip"):
            if current_area is not None:
                board_no_text = event.name.removeprefix("Board").removesuffix("Skip")
                if board_no_text.isdigit():
                    value = parse_bool(event.values[0]) if event.values else None
                    if value is not None:
                        current_area.board_skip[int(board_no_text)] = value
        elif event.name.startswith("Board") and event.name.endswith("Scan"):
            if current_area is not None:
                board_no_text = event.name.removeprefix("Board").removesuffix("Scan")
                if board_no_text.isdigit():
                    current_area.board_scan[int(board_no_text)] = parse_bool_list(event.values)
        elif event.name.startswith("Board") and event.name.endswith("Pt"):
            if current_area is not None:
                board_no_text = event.name.removeprefix("Board").removesuffix("Pt")
                if board_no_text.isdigit():
                    values = [value.strip() for value in event.values]
                    current_area.board_motion[int(board_no_text)] = {
                        "insert": values[0] if len(values) > 0 else None,
                        "attach": values[1] if len(values) > 1 else None,
                    }
        elif board_shift_no(event) is not None:
            shift_board_no = board_shift_no(event)
            attempt = last_closed_attempt or active_or_last_attempt()
            if attempt is not None and shift_board_no is not None:
                attempt.shift_board_no = shift_board_no
                set_attempt_board_no(attempt, shift_board_no)
        elif event.name.startswith("ILScanResult board"):
            text = event.name.replace("ILScanResult board", "").strip()
            pending_il_scan_board = int(text) if text.isdigit() else None
        elif event.name == "TakeBoardStart":
            if current_attempt is not None and current_attempt.set_end is None:
                current_attempt.source_end_line = current_attempt.source_end_line or (last_event.line_no if last_event else None)
                current_attempt = None
            attempt = ensure_attempt(event)
            if attempt is not None:
                attempt.take_start = event.timestamp
                attempt.source_start_line = event.line_no
        elif event.name == "TakeBoardEnd":
            attempt = ensure_attempt(event)
            if attempt is not None:
                attempt.take_end = event.timestamp
        elif event.name == "BoardSetStart":
            attempt = ensure_attempt(event)
            if attempt is not None:
                attempt.set_start = event.timestamp
                attempt.source_start_line = attempt.source_start_line or event.line_no
        elif event.name == "Column now":
            attempt = ensure_attempt(event)
            if attempt is not None:
                apply_area_coordinate(attempt, "column", parse_int(event.values), event)
        elif event.name == "Row now":
            attempt = ensure_attempt(event)
            if attempt is not None:
                apply_area_coordinate(attempt, "row", parse_int(event.values), event)
        elif event.name == "BoardNumber":
            attempt = ensure_attempt(event)
            if attempt is not None:
                attempt.board_number = parse_int(event.values)
        elif event.name == "BoardPrepareStart":
            if current_attempt is not None and current_attempt.set_start is not None:
                current_attempt.prepare_start = event.timestamp
        elif event.name == "BoardInsertStart":
            if current_attempt is not None:
                current_attempt.insert_start = event.timestamp
        elif event.name == "CanceledByForceSensor":
            attempt = active_or_last_attempt()
            if attempt is not None:
                attempt.force_sensor_branch = event.values[0].strip() if event.values else "Unknown"
                attempt.force_sensor_at = event.timestamp
                attempt.force_sensor_line = event.line_no
                attempt.source_end_line = attempt.source_end_line or event.line_no
        elif event.name == "NeedRemoveBoard":
            attempt = active_or_last_attempt()
            if attempt is not None:
                attempt.need_remove_board = True
                attempt.need_remove_at = event.timestamp
                attempt.need_remove_line = event.line_no
                attempt.source_end_line = attempt.source_end_line or event.line_no
                if attempt is current_attempt:
                    last_closed_attempt = attempt
                    current_attempt = None
        elif event.name == "BoardPrepareStopManual":
            attempt = active_or_last_attempt()
            if attempt is not None and current_area is not None:
                attempt.manual_stop = True
                attempt.manual_stop_line = event.line_no
            elif current_area is not None:
                current_area.warnings.append(f"Manual stop without active board attempt at line {event.line_no}")
        elif event.name == "BoardSetEnd":
            if current_attempt is not None:
                current_attempt.set_end = event.timestamp
                current_attempt.source_end_line = event.line_no
                last_closed_attempt = current_attempt
                current_attempt = None
        elif event.name == "ScanCompletedEnd":
            if current_area is not None:
                current_area.end_at = event.timestamp
                current_area.source_end_line = event.line_no
        elif event.name == "AreaCompleted":
            if current_area is not None:
                current_area.area_completed = parse_bool_list(event.values)
                current_area.end_at = event.timestamp or current_area.end_at
                current_area.source_end_line = event.line_no
                close_area(end_event=event)

        if event.timestamp is not None:
            last_timestamp_event = event
        last_event = event

    if current_session is not None:
        close_area("Log ended before AreaCompleted", end_event=last_event)
        if last_timestamp_event is not None:
            current_session.end_at = last_timestamp_event.timestamp or current_session.end_at
            current_session.source_end_line = last_timestamp_event.line_no

    result = AnalysisResult(
        file_name=file_name,
        parsed_at=datetime.now(),
        sessions=sessions,
        event_count=len(events),
        warnings=warnings,
        source_path=source_path,
        event_name_counts=dict(Counter(event.name for event in events)),
        force_branch_counts=dict(
            Counter(
                event.values[0].strip() if event.values else "Unknown"
                for event in events
                if event.name == "CanceledByForceSensor"
            )
        ),
        need_remove_count=sum(1 for event in events if event.name == "NeedRemoveBoard"),
    )
    resolve_board_numbers()
    for session in result.sessions:
        analyze_timings(session.areas)
        for area in session.areas:
            classify_area(area)
    return result
