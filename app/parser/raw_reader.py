from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List

from app.models import RawRow


def parse_csv_line(line: str) -> List[str]:
    reader = csv.reader([line], skipinitialspace=False)
    return next(reader)


def read_raw_rows(path: Path) -> List[RawRow]:
    rows: List[RawRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.rstrip("\r\n")
            if not raw.strip():
                continue
            rows.append(RawRow(line_no=line_no, raw=raw, cells=parse_csv_line(raw)))
    return rows


def rows_from_lines(lines: Iterable[str]) -> List[RawRow]:
    rows: List[RawRow] = []
    for line_no, raw_line in enumerate(lines, start=1):
        raw = raw_line.rstrip("\r\n")
        if raw.strip():
            rows.append(RawRow(line_no=line_no, raw=raw, cells=parse_csv_line(raw)))
    return rows

