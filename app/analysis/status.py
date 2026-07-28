from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from app.models import AreaCycle, BoardAttempt


STATUS_META = {
    "SKIPPED": {"label": "P", "text": "実施なし", "rank": 0},
    "NOT_ATTEMPTED": {"label": "-", "text": "実施ログなし", "rank": 1},
    "MANUAL_REMOVE": {"label": "除去", "text": "手動除去", "rank": 2},
    "FORCE_REVERSE": {"label": "逆", "text": "逆動作", "rank": 3},
    "FORCE_RELEASE": {"label": "Rel", "text": "BoardRelease", "rank": 4},
    "MANUAL_STOP": {"label": "停", "text": "手動停止", "rank": 5},
    "SUCCESS": {"label": "✓", "text": "成功", "rank": 6},
    "FAILED": {"label": "×", "text": "失敗", "rank": 7},
    "UNKNOWN": {"label": "?", "text": "不明", "rank": 8},
}

PHENOMENON_META = {
    "reverse": {"label": "逆再生"},
    "place": {"label": "置く"},
}


def attempts_by_board(area: AreaCycle) -> Dict[int, List[BoardAttempt]]:
    grouped: Dict[int, List[BoardAttempt]] = defaultdict(list)
    for attempt in area.board_attempts:
        if attempt.board_no is not None:
            grouped[attempt.board_no].append(attempt)
    return grouped


def raw_area_completed_value(area: AreaCycle, board_no: int) -> Optional[bool]:
    if area.area_completed is None or len(area.area_completed) < board_no:
        return None
    return area.area_completed[board_no - 1]


def has_pass_motion(area: AreaCycle, board_no: int) -> bool:
    motion = area.board_motion.get(board_no, {})
    return motion.get("insert") == "E" and motion.get("attach") == "E"


def has_planned_motion(area: AreaCycle, board_no: int) -> bool:
    motion = area.board_motion.get(board_no, {})
    return bool(motion.get("insert") or motion.get("attach"))


def status_for_attempt(attempt: BoardAttempt) -> str:
    if attempt.need_remove_board:
        return "MANUAL_REMOVE"
    if attempt.force_sensor_branch == "ReverseAction":
        return "FORCE_REVERSE"
    if attempt.force_sensor_branch == "BoardRelease":
        return "FORCE_RELEASE"
    if attempt.manual_stop:
        return "MANUAL_STOP"
    if attempt.set_end is not None:
        return "SUCCESS"
    return "UNKNOWN"


def board_status_for_area(area: AreaCycle, board_no: int) -> str:
    board_attempts = attempts_by_board(area).get(board_no, [])
    if area.board_skip.get(board_no) is True:
        return "SKIPPED"
    if board_attempts:
        return status_for_attempt(board_attempts[-1])
    if has_pass_motion(area, board_no):
        return "SKIPPED"
    if has_planned_motion(area, board_no):
        return "NOT_ATTEMPTED"
    return "UNKNOWN"


def classify_attempt_status(area: AreaCycle, attempt: BoardAttempt) -> str:
    if attempt.board_no is None:
        return "UNKNOWN"
    if area.board_skip.get(attempt.board_no) is True:
        return "SKIPPED"
    return status_for_attempt(attempt)


def classify_area(area: AreaCycle) -> None:
    for attempt in area.board_attempts:
        attempt.status = classify_attempt_status(area, attempt)


def attempt_phenomenon(attempt: BoardAttempt) -> Optional[str]:
    if attempt.force_sensor_branch == "ReverseAction" or attempt.need_remove_board:
        return "reverse"
    if attempt.force_sensor_branch == "BoardRelease":
        return "place"
    return None


def board_phenomenon(attempts: List[BoardAttempt]) -> Optional[str]:
    phenomena = [attempt_phenomenon(attempt) for attempt in attempts]
    if "reverse" in phenomena:
        return "reverse"
    if "place" in phenomena:
        return "place"
    return None


def board_card(area: AreaCycle, board_no: int) -> Dict[str, object]:
    grouped = attempts_by_board(area)
    attempts = grouped.get(board_no, [])
    attempt = attempts[-1] if attempts else None
    motion = area.board_motion.get(board_no, {})
    status = board_status_for_area(area, board_no)
    phenomenon = board_phenomenon(attempts)
    duration = None
    if attempt is not None:
        duration = attempt.install_duration_sec()
        if duration is None:
            duration = attempt.take_duration_sec()
    return {
        "board_no": board_no,
        "status": status,
        "status_label": STATUS_META[status]["label"],
        "status_text": STATUS_META[status]["text"],
        "phenomenon": phenomenon,
        "phenomenon_label": PHENOMENON_META[phenomenon]["label"] if phenomenon else None,
        "insert_motion": motion.get("insert") or (attempt.insert_motion if attempt else None),
        "attach_motion": motion.get("attach") or (attempt.attach_motion if attempt else None),
        "duration_sec": duration,
        "attempt_id": attempt.attempt_id if attempt else None,
        "attempt_count": len(attempts),
        "area_completed": raw_area_completed_value(area, board_no),
        "area_obstacle": area.area_obstacle[board_no - 1] if area.area_obstacle and len(area.area_obstacle) >= board_no else None,
        "board_scan": area.board_scan.get(board_no),
    }
