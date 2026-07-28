from pathlib import Path

from app.parser.state_machine import parse_log_file

ROOT = Path(__file__).resolve().parents[1]


def phase_by_label(area, label):
    return next(phase for phase in area.phases if phase.label == label)


def test_centering_and_install_durations_are_second_precision():
    result = parse_log_file(ROOT / "Work_20260110_113830_0908.csv")
    area = result.sessions[0].areas[0]

    assert phase_by_label(area, "車体位置調整").duration_sec == 14
    assert phase_by_label(area, "B3 取り付け").duration_sec == 27
    assert phase_by_label(area, "B3 ボード取得").duration_sec == 38


def test_reverse_action_spans_force_sensor_to_next_board_or_area_end():
    result = parse_log_file(ROOT / "0723ログ/Work_20260723_083922_3203.csv")
    area = result.sessions[0].areas[0]

    first_reverse = phase_by_label(area, "B3 逆再生")
    second_reverse = phase_by_label(area, "B2 逆再生")

    assert first_reverse.group == "reverse"
    assert first_reverse.duration_sec == 26
    assert first_reverse.source_start_line == 94
    assert first_reverse.source_end_line == 99
    assert second_reverse.group == "reverse"
    assert second_reverse.duration_sec == 20
    assert second_reverse.source_start_line == 106
    assert second_reverse.source_end_line == 112
    assert not any(phase.group == "manual" for phase in area.phases)


def test_board_release_spans_force_sensor_to_next_board():
    result = parse_log_file(ROOT / "Work_20260110_113830_0908.csv")
    phases = [
        phase
        for session in result.sessions
        for area in session.areas
        for phase in area.phases
        if phase.group == "place"
    ]

    first_place = phases[0]

    assert first_place.label == "B3 置く"
    assert first_place.duration_sec == 4
    assert first_place.source_start_line == 1633
    assert first_place.source_end_line == 1635
