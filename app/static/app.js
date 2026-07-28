const state = {
  summary: null,
  sessions: [],
  selectedSession: null,
  timeline: null,
  sessionTotals: null,
  grid: null,
  chartMode: "aggregate",
  mapForward: "up",
  mapShift: "left",
};

const COLORS = {
  move: "#2f6f9f",
  centering: "#278298",
  scan: "#6d5fa8",
  calc: "#b97921",
  take: "#2f8a62",
  install: "#3f7d45",
  reverse: "#b54848",
  place: "#b97921",
  abnormal: "#b54848",
  manual: "#8b4d9a",
  unclassified: "#63707a",
};

const GROUP_ORDER = [
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
];

const PHASE_ORDER = [
  "move",
  "centering",
  "il_scan_x",
  "d405_up",
  "il_scan_y",
  "il_scan_z",
  "obstacle_capture",
  "pattern_calc",
  "take_board",
  "pre_insert",
  "install",
  "force_reverse",
  "force_release",
  "manual_wait",
];

const INSERT_CORNERS = {
  1: { A: "top-right", B: "top-left", C: "bottom-left", D: "bottom-right" },
  2: { A: "top-left", B: "top-right", C: "bottom-right", D: "bottom-left" },
  3: { A: "bottom-left", B: "bottom-right", C: "top-right", D: "top-left" },
  4: { A: "bottom-right", B: "bottom-left", C: "top-left", D: "top-right" },
};

function directionAxis(direction) {
  return direction === "up" || direction === "down" ? "vertical" : "horizontal";
}

function oppositeDirection(direction) {
  return { up: "down", down: "up", left: "right", right: "left" }[direction];
}

function arrowForDirection(direction) {
  return { up: "↑", down: "↓", left: "←", right: "→" }[direction] || "?";
}

function rotateDirection(direction, frontDirection) {
  const rotations = {
    up: { up: "up", right: "right", down: "down", left: "left" },
    right: { up: "right", right: "down", down: "left", left: "up" },
    down: { up: "down", right: "left", down: "up", left: "right" },
    left: { up: "left", right: "up", down: "right", left: "down" },
  };
  return rotations[frontDirection]?.[direction] || direction;
}

function rotateCorner(corner, frontDirection) {
  const cornerDirections = {
    "top-right": ["up", "right"],
    "bottom-right": ["down", "right"],
    "bottom-left": ["down", "left"],
    "top-left": ["up", "left"],
  };
  const byDirections = {
    "up:right": "top-right",
    "right:up": "top-right",
    "down:right": "bottom-right",
    "right:down": "bottom-right",
    "down:left": "bottom-left",
    "left:down": "bottom-left",
    "up:left": "top-left",
    "left:up": "top-left",
  };
  const pair = cornerDirections[corner];
  if (!pair) return corner;
  const rotated = pair.map((direction) => rotateDirection(direction, frontDirection));
  return byDirections[rotated.join(":")] || corner;
}

function defaultShiftForForward(forward) {
  return directionAxis(forward) === "vertical" ? "left" : "up";
}

function $(selector) {
  return document.querySelector(selector);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function durationText(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest}s`;
}

function showMessage(text, isError = false) {
  const node = $("#message");
  node.textContent = text;
  node.style.background = isError ? "#b54848" : "#182026";
  node.classList.add("show");
  window.clearTimeout(showMessage.timer);
  showMessage.timer = window.setTimeout(() => node.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {
      detail = response.statusText;
    }
    throw new Error(detail);
  }
  return response.json();
}

async function loadLogs() {
  const payload = await api("/api/logs");
  const select = $("#log-select");
  select.innerHTML = "";
  for (const file of payload.files) {
    const option = document.createElement("option");
    option.value = file.filename;
    option.textContent = `${file.filename} (${file.source})`;
    select.appendChild(option);
  }
  if (!payload.files.length) {
    const option = document.createElement("option");
    option.textContent = "CSVがありません";
    select.appendChild(option);
  }
}

async function parseSelectedLog() {
  const filename = $("#log-select").value;
  if (!filename) return;
  showMessage("解析中...");
  const payload = await api("/api/logs/parse", {
    method: "POST",
    body: JSON.stringify({ filename }),
  });
  state.summary = payload.summary;
  state.sessions = payload.analysis.sessions;
  state.selectedSession = state.sessions[0]?.session_no ?? null;
  $("#current-file").textContent = `${payload.summary.file_name} / ${payload.summary.event_count} events`;
  renderSummary();
  renderSessions();
  await loadSessionViews();
  showMessage("解析しました");
}

async function uploadLog(file) {
  const form = new FormData();
  form.append("file", file);
  showMessage("アップロード解析中...");
  const response = await fetch("/api/logs/upload", { method: "POST", body: form });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || response.statusText);
  }
  const payload = await response.json();
  await loadLogs();
  $("#log-select").value = payload.file.filename;
  state.summary = payload.summary;
  state.sessions = payload.analysis.sessions;
  state.selectedSession = state.sessions[0]?.session_no ?? null;
  $("#current-file").textContent = `${payload.summary.file_name} / ${payload.summary.event_count} events`;
  renderSummary();
  renderSessions();
  await loadSessionViews();
  showMessage("アップロードしました");
}

function renderSummary() {
  const summary = state.summary;
  if (!summary) return;
  const counts = summary.status_counts || {};
  const force = summary.force_branch_counts || {};
  const cards = [
    ["セッション", summary.session_count],
    ["AreaCycle", summary.area_count],
    ["Board試行", summary.board_attempt_count],
    ["成功", counts.SUCCESS || 0],
    ["P", counts.SKIPPED || 0],
    ["実施ログなし", counts.NOT_ATTEMPTED || 0],
    ["失敗", counts.FAILED || 0],
    ["逆再生", force.ReverseAction || 0],
    ["置く", force.BoardRelease || 0],
    ["NeedRemove", summary.need_remove_count || 0],
    ["警告", summary.warning_count || 0],
  ];
  $("#summary-cards").innerHTML = cards
    .map(([label, value]) => `
      <article class="stat-card">
        <div class="stat-label">${escapeHtml(label)}</div>
        <div class="stat-value">${escapeHtml(value)}</div>
      </article>
    `)
    .join("");
}

function renderSessions() {
  const tabs = $("#session-tabs");
  tabs.innerHTML = "";
  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `S${session.session_no}`;
    button.className = session.session_no === state.selectedSession ? "active" : "";
    button.addEventListener("click", async () => {
      state.selectedSession = session.session_no;
      renderSessions();
      await loadSessionViews();
    });
    tabs.appendChild(button);
  }
}

async function loadSessionViews() {
  if (state.selectedSession === null) return;
  const suffix = `?session_no=${encodeURIComponent(state.selectedSession)}`;
  const [timeline, sessionTotals, grid] = await Promise.all([
    api(`/api/analysis/timeline${suffix}`),
    api("/api/analysis/session-totals"),
    api(`/api/analysis/grid${suffix}`),
  ]);
  state.timeline = timeline;
  state.sessionTotals = sessionTotals;
  state.grid = grid;
  renderChart();
  renderSessionTotalChart();
  renderDirectionMap();
}

function segmentColor(segment) {
  return COLORS[segment.group] || COLORS[segment.phase_id] || "#63707a";
}

function phaseRank(phaseId) {
  const index = PHASE_ORDER.findIndex((prefix) => phaseId === prefix || phaseId?.startsWith(`${prefix}_`));
  return index === -1 ? PHASE_ORDER.length : index;
}

function segmentRank(item) {
  if (state.chartMode === "detail") return phaseRank(item.phase_id);
  const index = GROUP_ORDER.indexOf(item.group);
  return index === -1 ? GROUP_ORDER.length : index;
}

function sortSeries(series) {
  return [...series].sort((left, right) => {
    const rankDiff = segmentRank(left) - segmentRank(right);
    if (rankDiff !== 0) return rankDiff;
    return left.label.localeCompare(right.label, "ja");
  });
}

function collectChartData() {
  const areas = state.timeline?.areas || [];
  const byLabel = new Map();
  const areaLabels = areas.map((area) => area.label);
  const areaIds = areas.map((area) => area.area_id);
  for (const area of areas) {
    const segments = state.chartMode === "aggregate" ? area.aggregate_segments : area.segments;
    for (const segment of segments) {
      const label = segment.label;
      if (!byLabel.has(label)) {
        byLabel.set(label, {
          label,
          phase_id: segment.phase_id,
          group: segment.group || segment.phase_id,
          values: Array(areas.length).fill(0),
        });
      }
      byLabel.get(label).values[areas.indexOf(area)] += segment.duration_sec || 0;
    }
  }
  return { areas, areaLabels, areaIds, series: sortSeries(Array.from(byLabel.values())) };
}

function renderChart() {
  const chart = $("#timeline-chart");
  const { areas, areaLabels, areaIds, series } = collectChartData();
  if (!areas.length) {
    chart.innerHTML = "<p class='muted'>表示できるAreaCycleがありません。</p>";
    return;
  }
  if (window.Plotly) {
    const traces = series.map((item) => ({
      x: areaLabels,
      y: item.values,
      customdata: areaIds,
      name: item.label,
      type: "bar",
      marker: { color: COLORS[item.group] || "#63707a" },
      hovertemplate: "%{x}<br>%{fullData.name}: %{y}s<extra></extra>",
    }));
    const layout = {
      barmode: "stack",
      margin: { l: 48, r: 16, t: 10, b: 90 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      yaxis: { title: "秒", gridcolor: "#d9e0e4" },
      xaxis: { tickangle: -45 },
      legend: { orientation: "h", y: -0.35 },
    };
    Plotly.newPlot(chart, traces, layout, { responsive: true, displaylogo: false });
    chart.on("plotly_click", (event) => {
      const areaId = event.points?.[0]?.customdata;
      if (areaId) openArea(areaId);
    });
    return;
  }
  renderFallbackChart(chart, areas);
}

function collectSessionTotalData() {
  const sessions = state.sessionTotals?.sessions || [];
  const byLabel = new Map();
  const labels = sessions.map((session) => session.label);
  const sessionNos = sessions.map((session) => session.session_no);
  for (const session of sessions) {
    for (const segment of session.segments) {
      const label = segment.label;
      if (!byLabel.has(label)) {
        byLabel.set(label, {
          label,
          phase_id: segment.phase_id,
          group: segment.group,
          values: Array(sessions.length).fill(0),
        });
      }
      byLabel.get(label).values[sessions.indexOf(session)] += segment.duration_sec || 0;
    }
  }
  return { sessions, labels, sessionNos, series: sortSeries(Array.from(byLabel.values())) };
}

function renderSessionTotalChart() {
  const chart = $("#session-total-chart");
  const { sessions, labels, sessionNos, series } = collectSessionTotalData();
  if (!sessions.length) {
    chart.innerHTML = "<p class='muted'>表示できるセッションがありません。</p>";
    return;
  }
  if (window.Plotly) {
    const traces = series.map((item) => ({
      x: labels,
      y: item.values,
      customdata: sessionNos,
      name: item.label,
      type: "bar",
      marker: { color: COLORS[item.group] || "#63707a" },
      hovertemplate: "%{x}<br>%{fullData.name}: %{y}s<extra></extra>",
    }));
    const layout = {
      barmode: "stack",
      margin: { l: 48, r: 16, t: 10, b: 70 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      yaxis: { title: "秒", gridcolor: "#d9e0e4" },
      xaxis: { tickangle: 0 },
      legend: { orientation: "h", y: -0.28 },
    };
    Plotly.newPlot(chart, traces, layout, { responsive: true, displaylogo: false });
    chart.on("plotly_click", async (event) => {
      const sessionNo = event.points?.[0]?.customdata;
      if (sessionNo) {
        state.selectedSession = sessionNo;
        renderSessions();
        await loadSessionViews();
      }
    });
    return;
  }
  renderFallbackSessionTotalChart(chart, sessions);
}

function renderFallbackSessionTotalChart(chart, sessions) {
  const maxTotal = Math.max(
    ...sessions.map((session) => session.segments.reduce((total, segment) => total + (segment.duration_sec || 0), 0)),
    1
  );
  chart.innerHTML = `
    <div class="fallback-chart">
      ${sessions.map((session) => `
        <div class="bar-row" data-session-no="${escapeHtml(session.session_no)}">
          <button type="button">${escapeHtml(session.label)}</button>
          <div class="bar-track">
            ${session.segments.map((segment) => `
              <span class="bar-segment"
                title="${escapeHtml(segment.label)} ${durationText(segment.duration_sec)}"
                style="width:${((segment.duration_sec || 0) / maxTotal) * 100}%; background:${segmentColor(segment)}"></span>
            `).join("")}
          </div>
        </div>
      `).join("")}
    </div>
  `;
  chart.querySelectorAll(".bar-row button").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedSession = Number(button.closest(".bar-row").dataset.sessionNo);
      renderSessions();
      await loadSessionViews();
    });
  });
}

function renderFallbackChart(chart, areas) {
  const maxTotal = Math.max(
    ...areas.map((area) =>
      (state.chartMode === "aggregate" ? area.aggregate_segments : area.segments)
        .reduce((total, segment) => total + (segment.duration_sec || 0), 0)
    ),
    1
  );
  chart.innerHTML = `
    <div class="fallback-chart">
      ${areas.map((area) => {
        const segments = state.chartMode === "aggregate" ? area.aggregate_segments : area.segments;
        return `
          <div class="bar-row" data-area-id="${escapeHtml(area.area_id)}">
            <button type="button">${escapeHtml(area.label)}</button>
            <div class="bar-track">
              ${segments.map((segment) => `
                <span class="bar-segment"
                  title="${escapeHtml(segment.label)} ${durationText(segment.duration_sec)}"
                  style="width:${((segment.duration_sec || 0) / maxTotal) * 100}%; background:${segmentColor(segment)}"></span>
              `).join("")}
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
  chart.querySelectorAll(".bar-row button").forEach((button) => {
    button.addEventListener("click", () => openArea(button.closest(".bar-row").dataset.areaId));
  });
}

function buildTraversal(columns, rows) {
  const plan = new Map();
  let sequence = 1;
  const forward = state.mapForward;
  const shift = state.mapShift;
  const forwardAxis = directionAxis(forward);

  if (forwardAxis === "vertical") {
    const columnsInOrder = shift === "left"
      ? Array.from({ length: columns }, (_, index) => columns - 1 - index)
      : Array.from({ length: columns }, (_, index) => index);
    columnsInOrder.forEach((column, laneIndex) => {
      const laneDirection = laneIndex % 2 === 0 ? forward : oppositeDirection(forward);
      const rowsInOrder = laneDirection === "up"
        ? Array.from({ length: rows }, (_, index) => index)
        : Array.from({ length: rows }, (_, index) => rows - 1 - index);
      rowsInOrder.forEach((row) => {
        plan.set(`${column}:${row}`, {
          sequence: sequence++,
          travelDirection: laneDirection,
          verticalDirection: laneDirection,
          horizontalDirection: shift,
        });
      });
    });
    return plan;
  }

  const rowsInOrder = shift === "up"
    ? Array.from({ length: rows }, (_, index) => index)
    : Array.from({ length: rows }, (_, index) => rows - 1 - index);
  rowsInOrder.forEach((row, laneIndex) => {
    const laneDirection = laneIndex % 2 === 0 ? forward : oppositeDirection(forward);
    const columnsInOrder = laneDirection === "left"
      ? Array.from({ length: columns }, (_, index) => columns - 1 - index)
      : Array.from({ length: columns }, (_, index) => index);
    columnsInOrder.forEach((column) => {
      plan.set(`${column}:${row}`, {
        sequence: sequence++,
        travelDirection: laneDirection,
        verticalDirection: shift,
        horizontalDirection: laneDirection,
      });
    });
  });
  return plan;
}

function insertCorner(boardNo, motion) {
  return INSERT_CORNERS[boardNo]?.[motion] || null;
}

function attachArrow(boardNo, motion, cellPlan) {
  if (motion === "A") return arrowForDirection(cellPlan?.travelDirection);
  if (motion === "B") return arrowForDirection(cellPlan?.horizontalDirection || cellPlan?.verticalDirection);
  if (motion === "C") {
    const direction = boardNo === 1 || boardNo === 2 ? "down" : "up";
    return arrowForDirection(rotateDirection(direction, state.mapForward));
  }
  if (motion === "D") {
    const direction = boardNo === 1 || boardNo === 4 ? "left" : "right";
    return arrowForDirection(rotateDirection(direction, state.mapForward));
  }
  return motion || "?";
}

function boardMapStateClass(board, isSkipped) {
  if (isSkipped) return "skipped";
  if (board.phenomenon === "reverse") return "reverse";
  if (board.phenomenon === "place") return "release";
  return "planned";
}

function renderDirectionMap() {
  const payload = state.grid;
  if (!payload) return;
  const map = $("#direction-map");
  const traversal = buildTraversal(payload.columns, payload.rows);
  const byPosition = new Map(payload.cells.map((cell) => [`${cell.column}:${cell.row}`, cell]));
  const areaCellsBySequence = payload.cells
    .filter((cell) => cell.area_id)
    .sort((left, right) => (left.area_seq || 0) - (right.area_seq || 0));
  const cellsInDisplayOrder = [];
  for (let row = payload.rows - 1; row >= 0; row -= 1) {
    for (let column = 0; column < payload.columns; column += 1) {
      const baseCell = byPosition.get(`${column}:${row}`) || { column, row, boards: [] };
      const cellPlan = traversal.get(`${column}:${row}`);
      const sequenceCell = cellPlan ? areaCellsBySequence[cellPlan.sequence - 1] : null;
      cellsInDisplayOrder.push({
        ...baseCell,
        planned_area: sequenceCell || null,
      });
    }
  }
  map.style.gridTemplateColumns = `repeat(${payload.columns}, var(--map-cell-size))`;
  map.innerHTML = cellsInDisplayOrder.map((cell) => renderMapCell(cell, traversal)).join("");
  map.querySelectorAll(".map-area-button[data-area-id]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openArea(button.dataset.areaId).catch((error) => showMessage(error.message, true));
    });
  });
  map.querySelectorAll(".map-board[data-board-info]").forEach((board) => {
    board.addEventListener("click", (event) => {
      event.stopPropagation();
      openMapBoard(board.dataset.boardInfo).catch((error) => showMessage(error.message, true));
    });
    board.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      event.stopPropagation();
      openMapBoard(board.dataset.boardInfo).catch((error) => showMessage(error.message, true));
    });
  });
}

function renderMapCell(cell, traversal) {
  const cellPlan = traversal.get(`${cell.column}:${cell.row}`);
  const sequence = cellPlan ? `#${cellPlan.sequence}` : "-";
  const area = cell.planned_area;
  if (!area) {
    return `
      <div class="map-cell empty">
        <div class="map-cell-label">
          <span class="map-sequence-plain">${escapeHtml(sequence)}</span>
          <span>C${cell.column} R${cell.row}</span>
        </div>
      </div>
    `;
  }
  return `
    <div class="map-cell">
      <div class="map-cell-label">
        <button type="button" class="map-area-button" data-area-id="${escapeHtml(area.area_id)}">${escapeHtml(sequence)}</button>
        <span>C${cell.column} R${cell.row} / A${area.area_seq}</span>
      </div>
      <div class="map-board-layout">
        ${area.boards.map((board) => renderMapBoard(board, cellPlan, area, cell)).join("")}
      </div>
    </div>
  `;
}

function renderMapBoard(board, cellPlan, area, cell) {
  const corner = rotateCorner(insertCorner(board.board_no, board.insert_motion), state.mapForward);
  const hasPassMotion = board.insert_motion === "E" && board.attach_motion === "E";
  let passReason = "";
  if (board.status === "SKIPPED") {
    passReason = "BoardSkip=True";
  } else if (hasPassMotion) {
    passReason = "E,E";
  }
  const isSkipped = Boolean(passReason);
  const stateClass = boardMapStateClass(board, isSkipped);
  const attemptAttr = board.attempt_id ? `data-attempt-id="${escapeHtml(board.attempt_id)}"` : "";
  const boardInfo = buildBoardInfo(board, area, cell, cellPlan, passReason);
  const boardInfoAttr = `data-board-info="${escapeHtml(JSON.stringify(boardInfo))}"`;
  if (isSkipped) {
    return `
      <div class="map-board b${board.board_no} ${stateClass}" role="button" tabindex="0" title="P: ${escapeHtml(passReason)}" ${attemptAttr} ${boardInfoAttr}>
        <span class="map-board-no">B${board.board_no}</span>
        <span class="pass-label">P</span>
      </div>
    `;
  }
  const insertMark = corner
    ? `<span class="insert-mark ${corner}" title="差し入れ ${escapeHtml(board.insert_motion)}">★</span>`
    : `<span class="insert-mark undefined" title="差し入れ ${escapeHtml(board.insert_motion || "?")}">${escapeHtml(board.insert_motion || "?")}</span>`;
  return `
    <div class="map-board b${board.board_no} ${stateClass}" role="button" tabindex="0" ${attemptAttr} ${boardInfoAttr}>
      <span class="map-board-no">B${board.board_no}</span>
      ${insertMark}
      <span class="attach-arrow" title="設置 ${escapeHtml(board.attach_motion || "?")}">${escapeHtml(attachArrow(board.board_no, board.attach_motion, cellPlan))}</span>
    </div>
  `;
}

function buildBoardInfo(board, area, cell, cellPlan = null, passReason = null) {
  return {
    ...board,
    pass_reason: passReason || null,
    session_no: area.session_no ?? state.grid?.session?.session_no ?? null,
    area_id: area.area_id,
    area_seq: area.area_seq,
    column: cell.column,
    row: cell.row,
    map_sequence: cellPlan?.sequence ?? null,
    travel_direction: cellPlan?.travelDirection ?? null,
  };
}

async function openArea(areaId) {
  const payload = await api(`/api/analysis/areas/${encodeURIComponent(areaId)}`);
  const area = payload.area;
  $("#detail-title").textContent = `Area ${area.area_seq}`;
  $("#detail-subtitle").textContent = `Session ${area.session_no} / C${area.column ?? "-"} R${area.row ?? "-"}`;
  $("#detail-content").innerHTML = renderAreaDetail(area);
  $("#detail-panel").classList.add("open");
}

async function openBoard(attemptId) {
  const payload = await api(`/api/analysis/boards/${encodeURIComponent(attemptId)}`);
  const attempt = payload.attempt;
  $("#detail-title").textContent = `Board ${attempt.board_no ?? "?"}`;
  $("#detail-subtitle").textContent = `Attempt ${attempt.attempt_no} / C${attempt.column ?? "-"} R${attempt.row ?? "-"}`;
  $("#detail-content").innerHTML = renderBoardDetail(attempt);
  $("#detail-panel").classList.add("open");
}

async function openMapBoard(boardInfoText) {
  const board = JSON.parse(boardInfoText);
  if (board.attempt_id) {
    await openBoard(board.attempt_id);
    return;
  }
  $("#detail-title").textContent = `Board ${board.board_no ?? "?"}`;
  $("#detail-subtitle").textContent = `Session ${board.session_no ?? "-"} / Area ${board.area_seq ?? "-"} / C${board.column ?? "-"} R${board.row ?? "-"}`;
  $("#detail-content").innerHTML = renderMapBoardDetail(board);
  $("#detail-panel").classList.add("open");
}

function renderAreaDetail(area) {
  return `
    <section class="detail-section">
      <h3>工程時間</h3>
      ${renderTable(["工程", "開始", "終了", "秒", "根拠行", "信頼度"], area.phases.map((phase) => [
        phase.label,
        phase.start_at || "-",
        phase.end_at || "-",
        durationText(phase.duration_sec),
        `${phase.source_start_line || "-"} → ${phase.source_end_line || "-"}`,
        phase.confidence,
      ]))}
    </section>
    <section class="detail-section">
      <h3>位置調整</h3>
      ${renderTable(["行", "時刻", "X", "Y", "Z", "Gamma", "AreaOblstacle"], area.centering_values.map((sample) => [
        sample.line_no,
        sample.at || "-",
        sample.x ?? "-",
        sample.y ?? "-",
        sample.z ?? "-",
        sample.gamma ?? "-",
        JSON.stringify(sample.area_obstacle),
      ]))}
    </section>
    <section class="detail-section">
      <h3>Board</h3>
      ${renderTable(["Board", "状態", "差入", "取付", "取得", "取付時間", "力センサ", "NeedRemove"], area.board_attempts.map((attempt) => [
        `B${attempt.board_no ?? "?"}`,
        attempt.status,
        attempt.insert_motion || "-",
        attempt.attach_motion || "-",
        durationText(attempt.take_duration_sec),
        durationText(attempt.install_duration_sec),
        attempt.force_sensor_branch || "-",
        attempt.need_remove_board ? "True" : "False",
      ]))}
    </section>
    <section class="detail-section">
      <h3>障害物・参考値</h3>
      ${renderKeyValue({
        AreaOblstacle: JSON.stringify(area.area_obstacle),
        "AreaCompleted（状態判定未使用）": JSON.stringify(area.area_completed),
        BoardSkip: JSON.stringify(area.board_skip),
        BoardScan: JSON.stringify(area.board_scan),
        BoardMotion: JSON.stringify(area.board_motion),
      })}
    </section>
    <section class="detail-section">
      <h3>警告</h3>
      ${area.warnings.length ? `<ul>${area.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : "<p class='muted'>なし</p>"}
    </section>
    <section class="detail-section">
      <h3>元ログ行</h3>
      ${renderRawEvents(area.raw_events)}
    </section>
  `;
}

function renderBoardDetail(attempt) {
  return `
    <section class="detail-section">
      <h3>BoardAttempt</h3>
      ${renderKeyValue({
        attempt_id: attempt.attempt_id,
        status: attempt.status,
        board_no: attempt.board_no,
        board_number: attempt.board_number,
        shift_board_no: attempt.shift_board_no,
        attempt_no: attempt.attempt_no,
        column: attempt.column,
        row: attempt.row,
        take_start: attempt.take_start,
        take_end: attempt.take_end,
        set_start: attempt.set_start,
        prepare_start: attempt.prepare_start,
        insert_start: attempt.insert_start,
        set_end: attempt.set_end,
        insert_motion: attempt.insert_motion,
        attach_motion: attempt.attach_motion,
        force_sensor_branch: attempt.force_sensor_branch,
        need_remove_board: attempt.need_remove_board,
        manual_stop: attempt.manual_stop,
        source_line: `${attempt.source_start_line || "-"} → ${attempt.source_end_line || "-"}`,
      })}
    </section>
  `;
}

function renderMapBoardDetail(board) {
  return `
    <section class="detail-section">
      <h3>Board</h3>
      ${renderKeyValue({
        area_id: board.area_id,
        map_sequence: board.map_sequence ? `#${board.map_sequence}` : "-",
        board_no: board.board_no,
        status: `${board.status_label || "-"} / ${board.status_text || board.status || "-"}`,
        pass_reason: board.pass_reason || "-",
        insert_motion: board.insert_motion,
        attach_motion: board.attach_motion,
        attempt_count: board.attempt_count,
        area_completed: board.area_completed,
        area_obstacle: board.area_obstacle,
        board_scan: JSON.stringify(board.board_scan ?? null),
        travel_direction: board.travel_direction ? arrowForDirection(board.travel_direction) : "-",
      })}
    </section>
  `;
}

function exportCsv(kind) {
  if (state.selectedSession === null) {
    showMessage("解析結果がありません", true);
    return;
  }
  const endpoint = kind === "timing" ? "timing" : "direction-map";
  const params = new URLSearchParams({
    session_no: String(state.selectedSession),
    forward: state.mapForward,
    shift: state.mapShift,
  });
  window.location.href = `/api/analysis/export/${endpoint}?${params.toString()}`;
}

function exportTimingCsv() {
  exportCsv("timing");
}

function exportDirectionMapCsv() {
  exportCsv("direction-map");
}

function updateMapDirectionButtons() {
  if (directionAxis(state.mapForward) === directionAxis(state.mapShift)) {
    state.mapShift = defaultShiftForForward(state.mapForward);
  }
  const frontLabel = $("#front-label");
  if (frontLabel) {
    frontLabel.textContent = `施工方向 ${arrowForDirection(state.mapForward)}`;
  }
  document.querySelectorAll("#forward-buttons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.direction === state.mapForward);
  });
  document.querySelectorAll("#shift-buttons button").forEach((button) => {
    const sameAxis = directionAxis(button.dataset.direction) === directionAxis(state.mapForward);
    button.disabled = sameAxis;
    button.classList.toggle("active", button.dataset.direction === state.mapShift);
  });
}

function renderKeyValue(values) {
  return `
    <table>
      <tbody>
        ${Object.entries(values).map(([key, value]) => `
          <tr><th>${escapeHtml(key)}</th><td>${escapeHtml(value ?? "-")}</td></tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderTable(headers, rows) {
  if (!rows.length) return "<p class='muted'>なし</p>";
  return `
    <table>
      <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function renderRawEvents(events) {
  return `
    <table class="raw-table">
      <thead><tr><th>行</th><th>時刻</th><th>Event</th><th>Raw</th></tr></thead>
      <tbody>
        ${events.map((event) => `
          <tr>
            <td>${event.line_no}</td>
            <td>${escapeHtml(event.timestamp || "-")}</td>
            <td>${escapeHtml(event.name)}</td>
            <td>${escapeHtml(event.raw)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function bindEvents() {
  $("#parse-button").addEventListener("click", () => {
    parseSelectedLog().catch((error) => showMessage(error.message, true));
  });
  $("#export-timing-button").addEventListener("click", exportTimingCsv);
  $("#export-direction-button").addEventListener("click", exportDirectionMapCsv);
  $("#upload-input").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) uploadLog(file).catch((error) => showMessage(error.message, true));
  });
  $("#detail-close").addEventListener("click", () => $("#detail-panel").classList.remove("open"));
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.chartMode = button.dataset.mode;
      document.querySelectorAll(".mode-button").forEach((node) => node.classList.toggle("active", node === button));
      renderChart();
    });
  });
  document.querySelectorAll("#forward-buttons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.mapForward = button.dataset.direction;
      if (directionAxis(state.mapForward) === directionAxis(state.mapShift)) {
        state.mapShift = defaultShiftForForward(state.mapForward);
      }
      updateMapDirectionButtons();
      renderDirectionMap();
    });
  });
  document.querySelectorAll("#shift-buttons button").forEach((button) => {
    button.addEventListener("click", () => {
      if (directionAxis(button.dataset.direction) === directionAxis(state.mapForward)) return;
      state.mapShift = button.dataset.direction;
      updateMapDirectionButtons();
      renderDirectionMap();
    });
  });
  updateMapDirectionButtons();
}

async function init() {
  bindEvents();
  try {
    await loadLogs();
    if ($("#log-select").value) {
      await parseSelectedLog();
    }
  } catch (error) {
    showMessage(error.message, true);
  }
}

document.addEventListener("DOMContentLoaded", init);
