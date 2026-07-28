from pathlib import Path

from app.analysis.summary import (
    build_direction_map_export_rows,
    build_session_totals,
    build_timeline,
    build_timing_export_rows,
)
from app.parser.state_machine import parse_log_file

ROOT = Path(__file__).resolve().parents[1]


def test_session_totals_builds_one_stacked_bar_payload_per_session():
    result = parse_log_file(ROOT / "0722ログ/Work_20260722_084516_2571.csv")
    payload = build_session_totals(result)

    assert len(payload["sessions"]) == 8
    assert payload["sessions"][0]["label"] == "S1"
    assert payload["sessions"][0]["segments"]
    assert any(segment["group"] == "install" for segment in payload["sessions"][0]["segments"])


def test_timeline_and_session_totals_order_move_before_centering():
    result = parse_log_file(ROOT / "0722ログ/Work_20260722_084516_2571.csv")
    timeline = build_timeline(result, session_no=1)
    area_with_move = next(
        area
        for area in timeline["areas"]
        if any(segment["group"] == "move" for segment in area["aggregate_segments"])
    )
    session_total = build_session_totals(result)["sessions"][0]

    assert [segment["group"] for segment in area_with_move["aggregate_segments"][:2]] == ["move", "centering"]
    assert [segment["group"] for segment in session_total["segments"][:2]] == ["move", "centering"]


def test_timing_export_rows_use_requested_headers_and_map_sequence():
    result = parse_log_file(ROOT / "0723ログ/Work_20260723_083922_3203.csv")
    rows = build_timing_export_rows(result, session_no=1, forward="up", shift="left")

    assert rows[0] == ["マス", "移動", "位置調整", "スキャン", "計算", "ボード取得", "取り付け", "逆再生", "置く"]
    assert rows[1][0] == 1
    assert len(rows[1]) == len(rows[0])


def test_direction_map_export_rows_use_board_number_order_and_e_for_pass():
    result = parse_log_file(ROOT / "0723ログ/Work_20260723_083922_3203.csv")
    rows = build_direction_map_export_rows(result, session_no=1, forward="up", shift="left")

    assert rows[0] == ["マス", "ボード", "差し入れ", "取り付けパターン"]
    assert rows[1:5] == [
        [1, "B1", "B", "A"],
        [1, "B2", "B", "A"],
        [1, "B3", "A", "D"],
        [1, "B4", "A", "D"],
    ]
    assert rows[7] == [2, "B3", "E", "E"]
