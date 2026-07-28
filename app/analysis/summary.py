from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional

from app.analysis.status import STATUS_META, board_card, board_status_for_area
from app.models import AnalysisResult, AreaCycle, BoardAttempt, Session


GROUP_LABELS = {
    "move": "移動",
    "centering": "位置調整",
    "scan": "スキャン",
    "calc": "計算・選択",
    "take": "ボード取得",
    "install": "取り付け",
    "reverse": "逆再生",
    "place": "置く",
    "abnormal": "異常対応",
    "manual": "手動対応",
    "unclassified": "未分類",
}

GROUP_ORDER = [
    "move",
    "centering",
    "scan",
    "calc",
    "take",
    "install",
    "reverse",
    "place",
    "manual",
    "abnormal",
    "unclassified",
]

EXPORT_GROUPS = [
    ("move", "移動"),
    ("centering", "位置調整"),
    ("scan", "スキャン"),
    ("calc", "計算"),
    ("take", "ボード取得"),
    ("install", "取り付け"),
    ("reverse", "逆再生"),
    ("place", "置く"),
]

DIRECTIONS = {"up", "down", "left", "right"}


def group_rank(group: str) -> int:
    return GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)


def sort_segments(segments: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return sorted(segments, key=lambda segment: group_rank(str(segment["group"])))


def iter_areas(result: AnalysisResult) -> Iterable[AreaCycle]:
    for session in result.sessions:
        for area in session.areas:
            yield area


def iter_attempts(result: AnalysisResult) -> Iterable[BoardAttempt]:
    for area in iter_areas(result):
        for attempt in area.board_attempts:
            yield attempt


def build_summary(result: AnalysisResult) -> Dict[str, object]:
    status_counts: Counter[str] = Counter()
    motion_counts: Counter[str] = Counter()
    warnings: List[str] = list(result.warnings)
    for session in result.sessions:
        warnings.extend(session.warnings)
        for area in session.areas:
            warnings.extend(area.warnings)
            for board_no in range(1, 5):
                status_counts[board_status_for_area(area, board_no)] += 1
                motion = area.board_motion.get(board_no)
                if motion:
                    motion_counts[f"{motion.get('insert') or '?'}->{motion.get('attach') or '?'}"] += 1

    attempts = list(iter_attempts(result))
    total_duration = sum(session.duration_sec() or 0 for session in result.sessions)
    return {
        "file_name": result.file_name,
        "parsed_at": result.parsed_at.strftime("%Y-%m-%d %H:%M:%S"),
        "event_count": result.event_count,
        "session_count": len(result.sessions),
        "area_count": sum(len(session.areas) for session in result.sessions),
        "board_attempt_count": len(attempts),
        "status_counts": {status: status_counts.get(status, 0) for status in STATUS_META},
        "status_meta": STATUS_META,
        "force_branch_counts": result.force_branch_counts,
        "need_remove_count": result.need_remove_count,
        "event_name_counts": result.event_name_counts,
        "motion_counts": dict(motion_counts),
        "total_duration_sec": total_duration,
        "warning_count": len(warnings),
        "warnings": warnings[:200],
        "sessions": [
            {
                "session_no": session.session_no,
                "start_at": session.start_at.strftime("%Y-%m-%d %H:%M:%S") if session.start_at else None,
                "end_at": session.end_at.strftime("%Y-%m-%d %H:%M:%S") if session.end_at else None,
                "duration_sec": session.duration_sec(),
                "columns": session.columns,
                "rows": session.rows,
                "area_count": len(session.areas),
                "board_loaded": session.board_loaded,
            }
            for session in result.sessions
        ],
    }


def find_session(result: AnalysisResult, session_no: Optional[int]) -> Optional[Session]:
    if not result.sessions:
        return None
    if session_no is None:
        return result.sessions[0]
    for session in result.sessions:
        if session.session_no == session_no:
            return session
    return None


def find_area(result: AnalysisResult, area_id: str) -> Optional[AreaCycle]:
    for area in iter_areas(result):
        if area.area_id == area_id:
            return area
    return None


def find_attempt(result: AnalysisResult, attempt_id: str) -> Optional[BoardAttempt]:
    for attempt in iter_attempts(result):
        if attempt.attempt_id == attempt_id:
            return attempt
    return None


def aggregate_segments(area: AreaCycle) -> List[Dict[str, object]]:
    totals: Dict[str, int] = defaultdict(int)
    for phase in area.phases:
        if phase.duration_sec is not None:
            totals[phase.group] += phase.duration_sec
    segments = [
        {
            "group": group,
            "label": GROUP_LABELS.get(group, group),
            "duration_sec": duration,
        }
        for group, duration in totals.items()
        if duration > 0
    ]
    return sort_segments(segments)


def direction_axis(direction: str) -> str:
    return "vertical" if direction in {"up", "down"} else "horizontal"


def opposite_direction(direction: str) -> str:
    return {"up": "down", "down": "up", "left": "right", "right": "left"}[direction]


def default_shift_for_forward(forward: str) -> str:
    return "left" if direction_axis(forward) == "vertical" else "up"


def normalize_map_directions(forward: Optional[str], shift: Optional[str]) -> tuple[str, str]:
    normalized_forward = forward if forward in DIRECTIONS else "up"
    normalized_shift = shift if shift in DIRECTIONS else default_shift_for_forward(normalized_forward)
    if direction_axis(normalized_forward) == direction_axis(normalized_shift):
        normalized_shift = default_shift_for_forward(normalized_forward)
    return normalized_forward, normalized_shift


def build_map_traversal(columns: int, rows: int, forward: str, shift: str) -> Dict[tuple[int, int], Dict[str, object]]:
    plan: Dict[tuple[int, int], Dict[str, object]] = {}
    sequence = 1
    forward_axis = direction_axis(forward)

    if forward_axis == "vertical":
        columns_in_order = range(columns - 1, -1, -1) if shift == "left" else range(columns)
        for lane_index, column in enumerate(columns_in_order):
            lane_direction = forward if lane_index % 2 == 0 else opposite_direction(forward)
            rows_in_order = range(rows) if lane_direction == "up" else range(rows - 1, -1, -1)
            for row in rows_in_order:
                plan[(column, row)] = {"sequence": sequence, "travel_direction": lane_direction}
                sequence += 1
        return plan

    rows_in_order = range(rows) if shift == "up" else range(rows - 1, -1, -1)
    for lane_index, row in enumerate(rows_in_order):
        lane_direction = forward if lane_index % 2 == 0 else opposite_direction(forward)
        columns_in_order = range(columns - 1, -1, -1) if lane_direction == "left" else range(columns)
        for column in columns_in_order:
            plan[(column, row)] = {"sequence": sequence, "travel_direction": lane_direction}
            sequence += 1
    return plan


def session_grid_size(session: Session) -> tuple[int, int]:
    max_column = max([area.column for area in session.areas if area.column is not None] + [session.columns - 1])
    max_row = max([area.row for area in session.areas if area.row is not None] + [session.rows - 1])
    return max(1, max_column + 1), max(1, max_row + 1)


def map_sequence_areas(session: Session, forward: Optional[str], shift: Optional[str]) -> List[tuple[int, Optional[AreaCycle]]]:
    columns, rows = session_grid_size(session)
    normalized_forward, normalized_shift = normalize_map_directions(forward, shift)
    traversal = build_map_traversal(columns, rows, normalized_forward, normalized_shift)
    areas_by_sequence = sorted(session.areas, key=lambda area: area.area_seq)
    entries: List[tuple[int, Optional[AreaCycle]]] = []
    for item in sorted(traversal.values(), key=lambda value: int(value["sequence"])):
        sequence = int(item["sequence"])
        area = areas_by_sequence[sequence - 1] if sequence - 1 < len(areas_by_sequence) else None
        entries.append((sequence, area))
    return entries


def build_timing_export_rows(
    result: AnalysisResult,
    session_no: Optional[int],
    forward: Optional[str],
    shift: Optional[str],
) -> List[List[object]]:
    session = find_session(result, session_no)
    rows: List[List[object]] = [["マス", *[label for _, label in EXPORT_GROUPS]]]
    if session is None:
        return rows
    for sequence, area in map_sequence_areas(session, forward, shift):
        totals: Dict[str, int] = defaultdict(int)
        if area is not None:
            for phase in area.phases:
                if phase.duration_sec is not None:
                    totals[phase.group] += phase.duration_sec
        rows.append([sequence, *[totals[group] for group, _ in EXPORT_GROUPS]])
    return rows


def build_direction_map_export_rows(
    result: AnalysisResult,
    session_no: Optional[int],
    forward: Optional[str],
    shift: Optional[str],
) -> List[List[object]]:
    session = find_session(result, session_no)
    rows: List[List[object]] = [["マス", "ボード", "差し入れ", "取り付けパターン"]]
    if session is None:
        return rows
    for sequence, area in map_sequence_areas(session, forward, shift):
        boards = {board_no: board_card(area, board_no) for board_no in range(1, 5)} if area else {}
        for board_no in range(1, 5):
            board = boards.get(board_no)
            is_pass = board is not None and board["status"] == "SKIPPED"
            rows.append(
                [
                    sequence,
                    f"B{board_no}",
                    "E" if is_pass else (board.get("insert_motion") if board else "") or "",
                    "E" if is_pass else (board.get("attach_motion") if board else "") or "",
                ]
            )
    return rows


def build_timeline(result: AnalysisResult, session_no: Optional[int] = None) -> Dict[str, object]:
    session = find_session(result, session_no)
    if session is None:
        return {"session": None, "areas": []}
    areas = []
    for area in session.areas:
        areas.append(
            {
                "area_id": area.area_id,
                "area_seq": area.area_seq,
                "label": f"A{area.area_seq} ({area.column},{area.row})",
                "column": area.column,
                "row": area.row,
                "duration_sec": area.duration_sec(),
                "segments": [phase.to_dict() for phase in area.phases if phase.duration_sec is not None],
                "aggregate_segments": aggregate_segments(area),
                "warnings": area.warnings,
            }
        )
    return {"session": session.to_dict(detail=False), "areas": areas, "group_labels": GROUP_LABELS}


def build_session_totals(result: AnalysisResult) -> Dict[str, object]:
    sessions = []
    for session in result.sessions:
        totals: Dict[str, int] = defaultdict(int)
        for area in session.areas:
            for phase in area.phases:
                if phase.duration_sec is not None:
                    totals[phase.group] += phase.duration_sec
        sessions.append(
            {
                "session_no": session.session_no,
                "label": f"S{session.session_no}",
                "start_at": session.start_at.strftime("%Y-%m-%d %H:%M:%S") if session.start_at else None,
                "end_at": session.end_at.strftime("%Y-%m-%d %H:%M:%S") if session.end_at else None,
                "duration_sec": session.duration_sec(),
                "area_count": len(session.areas),
                "segments": sort_segments(
                    [
                        {
                            "group": group,
                            "label": GROUP_LABELS.get(group, group),
                            "duration_sec": duration,
                        }
                        for group, duration in totals.items()
                        if duration > 0
                    ]
                ),
            }
        )
    return {"sessions": sessions, "group_labels": GROUP_LABELS}


def build_grid(result: AnalysisResult, session_no: Optional[int] = None) -> Dict[str, object]:
    session = find_session(result, session_no)
    if session is None:
        return {"session": None, "columns": 0, "rows": 0, "cells": []}
    max_column = max([area.column for area in session.areas if area.column is not None] + [session.columns - 1])
    max_row = max([area.row for area in session.areas if area.row is not None] + [session.rows - 1])
    columns = max(1, max_column + 1)
    rows = max(1, max_row + 1)
    by_position: Dict[tuple[int, int], List[AreaCycle]] = defaultdict(list)
    for area in session.areas:
        if area.column is not None and area.row is not None:
            by_position[(area.column, area.row)].append(area)

    cells = []
    for row in range(rows):
        for column in range(columns):
            areas = by_position.get((column, row), [])
            selected = areas[-1] if areas else None
            cells.append(
                {
                    "column": column,
                    "row": row,
                    "area_count": len(areas),
                    "area_id": selected.area_id if selected else None,
                    "area_seq": selected.area_seq if selected else None,
                    "duration_sec": selected.duration_sec() if selected else None,
                    "boards": [board_card(selected, board_no) for board_no in range(1, 5)] if selected else [],
                    "warnings": selected.warnings if selected else [],
                }
            )
    return {
        "session": session.to_dict(detail=False),
        "columns": columns,
        "rows": rows,
        "cells": cells,
        "status_meta": STATUS_META,
    }
