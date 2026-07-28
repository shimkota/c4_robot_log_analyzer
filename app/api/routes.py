from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.analysis.summary import (
    build_direction_map_export_rows,
    build_grid,
    build_session_totals,
    build_summary,
    build_timing_export_rows,
    build_timeline,
    find_area,
    find_attempt,
)
from app.config import UPLOAD_DIR, ensure_runtime_dirs, list_log_files, load_settings, resolve_log_path, save_settings
from app.models import AnalysisResult
from app.parser.state_machine import parse_log_file

router = APIRouter(prefix="/api")
_current_analysis: Optional[AnalysisResult] = None


class ParseRequest(BaseModel):
    filename: str


class SettingsRequest(BaseModel):
    settings: Dict[str, Any]


def require_analysis() -> AnalysisResult:
    if _current_analysis is None:
        raise HTTPException(status_code=404, detail="No parsed log is loaded")
    return _current_analysis


def csv_response(rows: list[list[object]], filename: str) -> Response:
    buffer = StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerows(rows)
    encoded_name = quote(filename)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


def export_filename(result: AnalysisResult, session_no: Optional[int], kind: str) -> str:
    base_name = Path(result.file_name).stem or "analysis"
    session = f"S{session_no or result.sessions[0].session_no}" if result.sessions else "S"
    return f"{base_name}_{session}_{kind}.csv"


@router.get("/logs")
def logs() -> Dict[str, object]:
    return {"files": list_log_files()}


@router.post("/logs/parse")
def parse_log(request: ParseRequest) -> Dict[str, object]:
    global _current_analysis
    try:
        path = resolve_log_path(request.filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _current_analysis = parse_log_file(path)
    return {
        "analysis": _current_analysis.to_dict(detail=False),
        "summary": build_summary(_current_analysis),
    }


@router.post("/logs/upload")
async def upload_log(file: UploadFile = File(...)) -> Dict[str, object]:
    global _current_analysis
    ensure_runtime_dirs()
    safe_name = Path(file.filename or "uploaded.csv").name
    if not safe_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file is required")
    destination = UPLOAD_DIR / safe_name
    content = await file.read()
    destination.write_bytes(content)
    _current_analysis = parse_log_file(destination)
    return {
        "file": {"filename": safe_name, "size": len(content), "source": "upload"},
        "analysis": _current_analysis.to_dict(detail=False),
        "summary": build_summary(_current_analysis),
    }


@router.get("/analysis/summary")
def analysis_summary() -> Dict[str, object]:
    return build_summary(require_analysis())


@router.get("/analysis/sessions")
def analysis_sessions() -> Dict[str, object]:
    result = require_analysis()
    return {"sessions": [session.to_dict(detail=False) for session in result.sessions]}


@router.get("/analysis/timeline")
def analysis_timeline(session_no: Optional[int] = None) -> Dict[str, object]:
    return build_timeline(require_analysis(), session_no=session_no)


@router.get("/analysis/session-totals")
def analysis_session_totals() -> Dict[str, object]:
    return build_session_totals(require_analysis())


@router.get("/analysis/grid")
def analysis_grid(session_no: Optional[int] = None) -> Dict[str, object]:
    return build_grid(require_analysis(), session_no=session_no)


@router.get("/analysis/export/timing")
def export_timing(
    session_no: Optional[int] = None,
    forward: Optional[str] = None,
    shift: Optional[str] = None,
) -> Response:
    result = require_analysis()
    rows = build_timing_export_rows(result, session_no=session_no, forward=forward, shift=shift)
    return csv_response(rows, export_filename(result, session_no, "工程時間"))


@router.get("/analysis/export/direction-map")
def export_direction_map(
    session_no: Optional[int] = None,
    forward: Optional[str] = None,
    shift: Optional[str] = None,
) -> Response:
    result = require_analysis()
    rows = build_direction_map_export_rows(result, session_no=session_no, forward=forward, shift=shift)
    return csv_response(rows, export_filename(result, session_no, "方向マップ"))


@router.get("/analysis/areas/{area_id}")
def analysis_area(area_id: str) -> Dict[str, object]:
    area = find_area(require_analysis(), area_id)
    if area is None:
        raise HTTPException(status_code=404, detail=f"Area not found: {area_id}")
    return {"area": area.to_dict(detail=True)}


@router.get("/analysis/boards/{attempt_id}")
def analysis_board(attempt_id: str) -> Dict[str, object]:
    attempt = find_attempt(require_analysis(), attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail=f"Board attempt not found: {attempt_id}")
    return {"attempt": attempt.to_dict()}


@router.get("/settings")
def settings() -> Dict[str, object]:
    return {"settings": load_settings()}


@router.put("/settings")
def update_settings(request: SettingsRequest) -> Dict[str, object]:
    try:
        return {"settings": save_settings(request.settings)}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
