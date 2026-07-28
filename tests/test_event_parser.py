from datetime import datetime

from app.parser.event_parser import parse_bool_list, parse_event
from app.parser.raw_reader import rows_from_lines


def event_from_line(line: str):
    return parse_event(rows_from_lines([line])[0])


def test_timestamp_truncates_fraction_to_seconds():
    event = event_from_line("AutoStart,20260722_08:52:43_1646")

    assert event.timestamp == datetime(2026, 7, 22, 8, 52, 43)
    assert event.line_no == 1


def test_area_completed_without_timestamp_keeps_bool_order():
    event = event_from_line("AreaCompleted:,[True, False, False, True]")

    assert event.name == "AreaCompleted"
    assert parse_bool_list(event.values) == [True, False, False, True]


def test_board_motion_values_are_variable_csv_values():
    event = event_from_line("Board1Pt:,B,A")

    assert event.name == "Board1Pt"
    assert event.values == ["B", "A"]

