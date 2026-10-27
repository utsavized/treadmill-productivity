// Treadmill Productivity dashboard (spec UI / output).
"use strict";

const $ = (id) => document.getElementById(id);
const CATEGORY_LABELS = { high: "High", medium: "Medium", low: "Low", none: "None", unrated: "Unrated" };
const UNAVAILABLE = {
  no_sessions: "No walking sessions in this period",
  no_active_time: "No active computer time",
  all_unrated: "All active time is in apps without a category",
};
const APPS_SHOWN = 10;

let period = { preset: "today", start: null, end: null };
let showAllApps = false;
let chart = null;
let openWalk = null;
let awDown = false;

// ---------- formatting ----------

function localDate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function duration(seconds) {
  const m = Math.round(seconds / 60);
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

function time(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function dateTime(iso) {
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function pct(part, whole) {
  return whole > 0 ? `${Math.round((100 * part) / whole)}%` : "–";
}

function toLocalInput(iso) {
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${localDate(d)}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ---------- API ----------

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.message || (Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : res.statusText);
    throw Object.assign(new Error(msg), { status: res.status, code: data.error });
  }
  return data;
}

// ---------- period ----------

function currentRange() {
  const today = new Date();
  if (period.preset === "today") return [localDate(today), localDate(today)];
  if (period.preset === "week") {
    const start = new Date(today);
    start.setDate(start.getDate() - 6);
    return [localDate(start), localDate(today)];
  }
  return [period.start || localDate(today), period.end || localDate(today)];
}

function setPreset(preset) {
  period.preset = preset;
  document.querySelectorAll("[data-preset]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === preset)));
  $("custom-range").hidden = preset !== "custom";
  if (preset === "custom") {
    const [s, e] = currentRange();
    $("start-date").value = period.start = period.start || s;
    $("end-date").value = period.end = period.end || e;
  }
  refresh();
}

// ---------- status bar ----------

function renderStatus() {
  $("aw-down").hidden = !awDown;
  const banner = $("walking-banner");
  const btn = $("walk-toggle");
  if (openWalk) {
    const elapsed = (Date.now() - new Date(openWalk.started_at)) / 1000;
    banner.textContent = `Walking since ${time(openWalk.started_at)} (${duration(elapsed)}). Remember to press Stop.`;
    banner.hidden = false;
    btn.textContent = "Stop walking";
    btn.className = "stop";
  } else {
    banner.hidden = true;
    btn.textContent = "Start walking";
    btn.className = "primary";
  }
}

async function loadStatus() {
  const wasDown = awDown;
  try {
    const s = await api("GET", "/api/status");
    openWalk = s.open_walk;
    awDown = s.activitywatch !== "ok";
  } catch (e) {
    awDown = false;
  }
  renderStatus();
  if (wasDown && !awDown) loadReport();
}

async function toggleWalk() {
  $("walk-error").textContent = "";
  try {
    await api("POST", openWalk ? "/api/walks/stop" : "/api/walks/start");
  } catch (e) {
    $("walk-error").textContent = e.message;
  }
  await loadStatus();
  refresh();
}

// ---------- report ----------

function renderScore(el, cond) {
  if (cond.unavailable) {
    el.innerHTML = `<div class="reason">${esc(UNAVAILABLE[cond.unavailable])}</div>`;
  } else {
    el.innerHTML = `<div class="score">${cond.score.toFixed(2)}</div>`;
  }
  el.innerHTML += `<div class="muted">${duration(cond.active_s)} active · ${duration(cond.unrated_s)} unrated</div>`;
}

function renderVerdict(r) {
  const el = $("verdict");
  if (!r.verdict) {
    el.textContent = "Comparison unavailable: both conditions need rated active time.";
    el.className = "verdict muted";
    return;
  }
  el.className = "verdict";
  const diff = Math.abs(r.difference).toFixed(2);
  el.textContent = r.verdict === "equal" ? "Equal while walking and sitting" : `${r.verdict === "higher" ? "Higher" : "Lower"} while walking by ${diff}`;
}

function splitRows(rows, labelOf, w, s) {
  return rows
    .map(
      (row) =>
        `<tr><td>${esc(labelOf(row))}</td>` +
        `<td>${duration(row.walking_s)}</td><td>${pct(row.walking_s, w)}</td>` +
        `<td>${duration(row.sitting_s)}</td><td>${pct(row.sitting_s, s)}</td></tr>`
    )
    .join("");
}

function splitHeader(first) {
  return `<tr><th>${first}</th><th>Walking</th><th>%</th><th>Assumed sitting</th><th>%</th></tr>`;
}

function renderCategories(r) {
  const w = r.conditions.walking.active_s;
  const s = r.conditions.sitting.active_s;
  $("category-table").innerHTML = splitHeader("Category") + splitRows(r.categories, (c) => CATEGORY_LABELS[c.category], w, s);

  const data = {
    labels: r.categories.map((c) => CATEGORY_LABELS[c.category]),
    datasets: [
      { label: "Walking", data: r.categories.map((c) => c.walking_s / 60), backgroundColor: css("--series-walking") },
      { label: "Assumed sitting", data: r.categories.map((c) => c.sitting_s / 60), backgroundColor: css("--series-sitting") },
    ],
  };
  data.datasets.forEach((d) => Object.assign(d, { borderRadius: 4, borderSkipped: "bottom", borderWidth: 0, maxBarThickness: 28 }));
  if (typeof Chart === "undefined") return;
  if (chart) {
    chart.data = data;
    chart.update();
    return;
  }
  const grid = css("--border");
  const ink = css("--text-secondary");
  chart = new Chart($("category-chart"), {
    type: "bar",
    data,
    options: {
      maintainAspectRatio: false,
      datasets: { bar: { categoryPercentage: 0.7, barPercentage: 0.92 } },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top", align: "start", labels: { color: ink, boxWidth: 10, boxHeight: 10 } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${duration(ctx.raw * 60)}` } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: ink } },
        y: { beginAtZero: true, grid: { color: grid }, border: { display: false },
             ticks: { color: ink }, title: { display: true, text: "Minutes", color: ink } },
      },
    },
  });
}

function renderApps(r) {
  const w = r.conditions.walking.active_s;
  const s = r.conditions.sitting.active_s;
  const rows = showAllApps ? r.apps : r.apps.slice(0, APPS_SHOWN);
  $("app-table").innerHTML = r.apps.length
    ? splitHeader("App") + splitRows(rows, (a) => a.app, w, s)
    : `<tr><td class="muted">No active time in this period.</td></tr>`;
  const toggle = $("apps-toggle");
  toggle.hidden = r.apps.length <= APPS_SHOWN;
  toggle.textContent = showAllApps ? "Show top 10" : `Show all ${r.apps.length}`;
}

function renderCoverage(r) {
  const c = r.coverage;
  const dates = c.dates.length ? c.dates.join(", ") : "none";
  $("coverage").innerHTML =
    `<p>Dates with data: ${esc(dates)}<br>` +
    `Active time: walking ${duration(r.conditions.walking.active_s)}, assumed sitting ${duration(r.conditions.sitting.active_s)}</p>`;
  if (!c.gaps.length) {
    $("gap-table").innerHTML = `<tr><td class="muted">No collection gaps of 10 minutes or more.</td></tr>`;
    return;
  }
  const rows = c.gaps
    .map((g) => {
      const day = localDate(new Date(g.start));
      const len = (new Date(g.end) - new Date(g.start)) / 1000;
      return `<tr class="${g.during_walk ? "during-walk" : ""}"><td>${day}</td><td>${time(g.start)}–${time(g.end)}</td>` +
        `<td>${duration(len)}</td><td>${g.during_walk ? "During a walk" : ""}</td></tr>`;
    })
    .join("");
  $("gap-table").innerHTML = `<tr><th>Day</th><th>Gap</th><th>Length</th><th></th></tr>` + rows;
}

async function loadReport() {
  const [start, end] = currentRange();
  $("period-label").textContent = start === end ? start : `${start} to ${end}`;
  try {
    const r = await api("GET", `/api/report?start=${start}&end=${end}`);
    $("report-error").hidden = true;
    $("results").hidden = false;
    renderScore($("walking-score"), r.conditions.walking);
    renderScore($("sitting-score"), r.conditions.sitting);
    renderVerdict(r);
    renderCategories(r);
    renderApps(r);
    renderCoverage(r);
  } catch (e) {
    $("results").hidden = true;
    if (e.status === 503) {
      awDown = true;
      renderStatus();
      $("report-error").hidden = true;
    } else {
      $("report-error").textContent = e.message;
      $("report-error").hidden = false;
    }
  }
}

// ---------- sessions ----------

async function loadSessions() {
  const [start, end] = currentRange();
  const table = $("sessions");
  try {
    const walks = await api("GET", `/api/walks?start=${start}&end=${end}`);
    if (!walks.length) {
      table.innerHTML = `<tr><td class="muted">No walking sessions in this period.</td></tr>`;
      return;
    }
    table.innerHTML =
      `<tr><th>Start</th><th>End</th><th>Length</th><th></th></tr>` +
      walks
        .map((w) => {
          const end = w.ended_at ? dateTime(w.ended_at) : "open";
          const len = ((w.ended_at ? new Date(w.ended_at) : new Date()) - new Date(w.started_at)) / 1000;
          return `<tr data-id="${w.id}" data-start="${w.started_at}" data-end="${w.ended_at || ""}">` +
            `<td>${dateTime(w.started_at)}</td><td>${end}</td><td>${duration(len)}</td>` +
            `<td><button data-action="edit">Edit</button> <button data-action="delete">Delete</button></td></tr>`;
        })
        .join("");
  } catch (e) {
    $("sessions-error").textContent = e.message;
  }
}

function editRow(tr) {
  const open = !tr.dataset.end;
  tr.innerHTML =
    `<td><input type="datetime-local" step="1" name="start" value="${toLocalInput(tr.dataset.start)}"></td>` +
    `<td>${open ? '<span class="muted">open</span>' : `<input type="datetime-local" step="1" name="end" value="${toLocalInput(tr.dataset.end)}">`}</td>` +
    `<td></td><td><button data-action="save">Save</button> <button data-action="cancel">Cancel</button></td>`;
}

async function onSessionClick(ev) {
  const btn = ev.target.closest("button");
  if (!btn) return;
  const tr = btn.closest("tr");
  const id = tr.dataset.id;
  $("sessions-error").textContent = "";
  try {
    if (btn.dataset.action === "edit") return editRow(tr);
    if (btn.dataset.action === "cancel") return loadSessions();
    if (btn.dataset.action === "delete") {
      if (!confirm("Delete this walking session?")) return;
      await api("DELETE", `/api/walks/${id}`);
    }
    if (btn.dataset.action === "save") {
      const start = tr.querySelector('[name="start"]').value;
      const endInput = tr.querySelector('[name="end"]');
      await api("PATCH", `/api/walks/${id}`, {
        started_at: new Date(start).toISOString(),
        ended_at: endInput ? new Date(endInput.value).toISOString() : null,
      });
    }
  } catch (e) {
    $("sessions-error").textContent = e.message;
    return;
  }
  await loadStatus();
  refresh();
}

// ---------- wiring ----------

function refresh() {
  loadReport();
  loadSessions();
}

document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => setPreset(b.dataset.preset)));
$("start-date").addEventListener("change", (e) => { period.start = e.target.value; refresh(); });
$("end-date").addEventListener("change", (e) => { period.end = e.target.value; refresh(); });
$("walk-toggle").addEventListener("click", toggleWalk);
$("apps-toggle").addEventListener("click", () => { showAllApps = !showAllApps; loadReport(); });
$("sessions").addEventListener("click", onSessionClick);

loadStatus().then(refresh);
setInterval(loadStatus, 30000);
