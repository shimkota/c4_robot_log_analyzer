from pathlib import Path

from app.analysis.status import board_card, board_status_for_area
from app.models import RawRow
from app.parser.event_parser import parse_events
from app.parser.state_machine import build_analysis, parse_log_file

ROOT = Path(__file__).resolve().parents[1]


def parse_fixture(name: str):
    return parse_log_file(ROOT / name)


def parse_lines(lines: list[str]):
    rows = [RawRow(line_no=index, raw=line, cells=line.split(",")) for index, line in enumerate(lines, 1)]
    return build_analysis(parse_events(rows))


def test_workspace_logs_contain_eight_auto_start_sessions_total():
    first = parse_fixture("Work_20260110_113830_0908.csv")
    second = parse_fixture("Work_20260112_082222_1427.csv")

    assert len(first.sessions) == 5
    assert len(second.sessions) == 3
    assert len(first.sessions) + len(second.sessions) == 8


def test_design_target_log_reproduces_known_anomaly_event_counts():
    result = parse_fixture("0722ログ/Work_20260722_084516_2571.csv")

    assert len(result.sessions) == 8
    assert result.force_branch_counts["ReverseAction"] == 18
    assert result.force_branch_counts["BoardRelease"] == 8
    assert result.need_remove_count == 18


def test_lr_move_only_markers_are_not_empty_area_cycles():
    result = parse_fixture("0722ログ/Work_20260722_084516_2571.csv")
    first_session = result.sessions[0]

    assert len(first_session.areas) == 15
    assert all(area.column is not None and area.row is not None for area in first_session.areas)
    assert [(area.column, area.row) for area in first_session.areas[:6]] == [
        (2, 0),
        (2, 1),
        (2, 2),
        (2, 3),
        (2, 4),
        (1, 4),
    ]


def test_attempts_resolve_to_forward_installation_order_for_july_log():
    result = parse_fixture("0723ログ/Work_20260723_083922_3203.csv")
    area = result.sessions[0].areas[0]

    assert [
        (attempt.board_no, attempt.board_number, attempt.shift_board_no, attempt.need_remove_board)
        for attempt in area.board_attempts
    ] == [
        (4, 1, 4, False),
        (1, 2, 1, False),
        (3, 3, None, True),
        (2, 4, None, True),
    ]


def test_passed_board_is_removed_from_forward_installation_order():
    result = parse_lines(
        [
            "AutoStart,20260723_08:00:00_0000",
            "CenteringStart,20260723_08:00:01_0000",
            "Board1Skip,False",
            "Board2Skip,False",
            "Board3Skip,False",
            "Board4Skip,False",
            "Board1Pt:,A,D",
            "Board2Pt:,B,B",
            "Board3Pt:,E,E",
            "Board4Pt:,A,D",
            "TakeBoardStart,20260723_08:00:02_0000",
            "TakeBoardEnd,20260723_08:00:03_0000",
            "BoardSetStart,20260723_08:00:04_0000",
            "Column now:,0",
            "Row now:,0",
            "BoardNumber:,1",
            "BoardInsertStart,20260723_08:00:05_0000",
            "BoardSetEnd,20260723_08:00:06_0000",
            "TakeBoardStart,20260723_08:00:07_0000",
            "TakeBoardEnd,20260723_08:00:08_0000",
            "BoardSetStart,20260723_08:00:09_0000",
            "Column now:,0",
            "Row now:,0",
            "BoardNumber:,2",
            "BoardInsertStart,20260723_08:00:10_0000",
            "BoardSetEnd,20260723_08:00:11_0000",
            "TakeBoardStart,20260723_08:00:12_0000",
            "TakeBoardEnd,20260723_08:00:13_0000",
            "BoardSetStart,20260723_08:00:14_0000",
            "Column now:,0",
            "Row now:,0",
            "BoardNumber:,3",
            "BoardInsertStart,20260723_08:00:15_0000",
            "BoardSetEnd,20260723_08:00:16_0000",
            "AreaCompleted:,False,False,False,False",
        ]
    )
    area = result.sessions[0].areas[0]

    assert [(attempt.board_no, attempt.board_number) for attempt in area.board_attempts] == [
        (4, 1),
        (1, 2),
        (2, 3),
    ]
    assert board_card(area, 3)["status"] == "SKIPPED"


def test_board_status_and_phenomenon_are_separate_for_reverse_action():
    result = parse_fixture("0723ログ/Work_20260723_083922_3203.csv")
    area = result.sessions[0].areas[0]
    card = board_card(area, 3)

    assert card["status"] == "MANUAL_REMOVE"
    assert card["status_text"] == "手動除去"
    assert card["phenomenon"] == "reverse"
    assert card["phenomenon_label"] == "逆再生"


def test_board_release_phenomenon_does_not_depend_on_status_label():
    result = parse_fixture("Work_20260110_113830_0908.csv")
    card = next(
        board_card(area, board_no)
        for session in result.sessions
        for area in session.areas
        for board_no in range(1, 5)
        if board_card(area, board_no)["phenomenon"] == "place"
    )

    assert card["status"] == "FORCE_RELEASE"
    assert card["status_text"] == "BoardRelease"
    assert card["phenomenon"] == "place"
    assert card["phenomenon_label"] == "置く"


def test_first_area_keeps_coordinates_motion_and_completion_order():
    result = parse_fixture("Work_20260110_113830_0908.csv")
    area = result.sessions[0].areas[0]

    assert area.column == 0
    assert area.row == 0
    assert area.area_obstacle == [False, True, True, True]
    assert area.area_completed == [True, False, False, False]
    assert area.board_motion[1] == {"insert": "E", "attach": "E"}
    assert area.board_scan[2] == [True, True, True, True, False, True, False, True]


def test_board_skip_true_is_displayed_as_p_status():
    result = parse_fixture("Work_20260110_113830_0908.csv")
    skipped_area = next(
        area
        for session in result.sessions
        for area in session.areas
        if area.board_skip.get(1) is True
    )

    assert board_status_for_area(skipped_area, 1) == "SKIPPED"


def test_area_completed_is_not_used_for_board_status():
    result = parse_fixture("0723ログ/Work_20260723_083922_3203.csv")
    area_9 = result.sessions[1].areas[8]
    area_12 = result.sessions[1].areas[11]

    assert area_9.area_id == "S2-A9"
    assert area_9.area_completed == [False, False, False, True]
    assert board_card(area_9, 4)["status"] == "SKIPPED"
    assert board_card(area_9, 4)["status_text"] == "実施なし"

    assert area_12.area_id == "S2-A12"
    assert area_12.area_completed == [False, True, False, False]
    assert board_card(area_12, 1)["status"] == "MANUAL_REMOVE"
    assert board_card(area_12, 1)["status_text"] == "手動除去"
    assert board_card(area_12, 2)["status"] == "NOT_ATTEMPTED"
    assert board_card(area_12, 2)["status_text"] == "実施ログなし"
    assert board_card(area_12, 3)["status"] == "SUCCESS"


def test_force_sensor_attempt_does_not_merge_with_later_success():
    result = parse_fixture("0723ログ/Work_20260723_083922_3203.csv")
    area = result.sessions[1].areas[11]
    reverse_card = board_card(area, 1)
    skipped_card = board_card(area, 2)
    success_card = board_card(area, 3)

    assert reverse_card["status"] == "MANUAL_REMOVE"
    assert reverse_card["phenomenon"] == "reverse"
    assert skipped_card["status"] == "NOT_ATTEMPTED"
    assert success_card["status"] == "SUCCESS"
    assert success_card["phenomenon"] is None


def test_force_sensor_on_s3_area_9_maps_to_non_pass_board():
    result = parse_fixture("0721ログ/Work_20260721_085549_3961.csv")
    area = result.sessions[2].areas[8]

    assert area.area_id == "S3-A9"
    assert board_card(area, 1)["status"] == "SUCCESS"
    assert board_card(area, 2)["status"] == "MANUAL_REMOVE"
    assert board_card(area, 2)["phenomenon"] == "reverse"
    assert board_card(area, 3)["status"] == "SKIPPED"
    assert board_card(area, 4)["status"] == "SKIPPED"


def test_force_sensor_on_s3_area_14_maps_to_non_pass_board():
    result = parse_fixture("0721ログ/Work_20260721_085549_3961.csv")
    area = result.sessions[2].areas[13]

    assert area.area_id == "S3-A14"
    assert board_card(area, 1)["status"] == "SKIPPED"
    assert board_card(area, 4)["status"] == "MANUAL_REMOVE"
    assert board_card(area, 4)["phenomenon"] == "reverse"
    assert board_card(area, 3)["status"] == "SUCCESS"
    assert board_card(area, 2)["status"] == "SUCCESS"


def test_force_sensor_attempts_follow_installation_order_not_shift_lines():
    result = parse_fixture("0721ログ/Work_20260721_085549_3961.csv")
    area = result.sessions[7].areas[2]

    assert area.area_id == "S8-A3"
    assert [
        (attempt.board_no, attempt.board_number, attempt.shift_board_no, attempt.force_sensor_branch)
        for attempt in area.board_attempts
    ] == [
        (4, 1, 4, None),
        (1, 2, 1, None),
        (3, 3, None, "ReverseAction"),
        (2, 4, None, "ReverseAction"),
    ]
    assert board_card(area, 1)["status"] == "SUCCESS"
    assert board_card(area, 4)["status"] == "SUCCESS"
    assert board_card(area, 2)["phenomenon"] == "reverse"
    assert board_card(area, 3)["phenomenon"] == "reverse"
