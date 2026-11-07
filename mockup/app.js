// Imbalance Watch: a plain-JS mockup of the notification chat on top of the event classifiers.
// Data: /api/meta, /api/forecast, /api/actuals and /api/notes from the backend API (same origin).
// Nothing here computes a forecast: the API serves only data usable at the viewing time.
"use strict";

const TZ = "Europe/Helsinki";
const HOUR = 3600e3;
const LOOKBACK = 12 * HOUR;
const RISE = 0.10;                 // re-notify when a firing note's probability rises this much
const MAX_NEW_PER_UPDATE = 4;      // keep the chat readable during replay
// The chat speaks up only above a stricter bar than the API's default note threshold: at the defaults
// about 7 of 21 notes fire per hour, at max(2x usual rate, 30 %) a median of 2, and none in a third of
// hours (measured on validation origins only, never test).
const chatBar = (n) => Math.min(0.8, Math.max(n.threshold, 2 * n.base_rate, 0.3));
const loud = (n) => n.probability >= chatBar(n);
const SEVERITY = { spike_high: "hi", extreme_price: "hi", forecast_miss: "hi", spike_low: "lo",
                   deep_negative: "lo", large_down_activation: "lo" };
const CONFIDENCE_TEXT = {
  high: "the inputs are fresh, the models agree and many similar past cases back it up",
  medium: "either the calibration range is wider than usual or the price models disagree",
  low: "the data is stale or there were few similar past cases, so treat it as a hint",
};

const state = { meta: null, asOf: null, origin: null, forecast: null, actuals: null, notes: [],
                seen: new Map(), highlight: null, timer: null, notify: false, activeMsg: null };
const $ = (id) => document.getElementById(id);

// ---------- formatting ----------
const timeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const dateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "numeric",
                                                   month: "short", hour: "2-digit", minute: "2-digit" });
const hm = (t) => timeFmt.format(new Date(t));
const pct = (p) => `${Math.round(p * 100)} %`;
const pctRange = (lo, hi) => `${Math.round(lo * 100)}–${Math.round(hi * 100)} %`;
const iso = (t) => new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const listText = (xs) => xs.length <= 1 ? (xs[0] || "") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;

async function api(path, params = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null));
  const res = await fetch(`/api/${path}?${query}`);
  if (!res.ok) throw new Error(`${path}: ${res.status} ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

// ---------- charts (hand-made SVG, no library) ----------
const NS = "http://www.w3.org/2000/svg";
function el(name, attrs = {}, parent) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function niceTicks(min, max, count = 5) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

function drawChart(svg, { x0, x1, yMin, yMax, yFmt, series = [], band = null, nowT = null, highlight = null }) {
  svg.replaceChildren();
  const W = svg.clientWidth || 600, H = svg.clientHeight || 300;
  const m = { l: 46, r: 12, t: 10, b: 24 };
  const sx = (t) => m.l + ((t - x0) / (x1 - x0)) * (W - m.l - m.r);
  const sy = (v) => H - m.b - ((v - yMin) / (yMax - yMin)) * (H - m.t - m.b);
  el("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent" }, svg);

  for (const v of niceTicks(yMin, yMax)) {
    el("line", { x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v), class: "grid" }, svg);
    el("text", { x: m.l - 6, y: sy(v) + 4, "text-anchor": "end" }, svg).textContent = yFmt(v);
  }
  const first = Math.ceil(x0 / (2 * HOUR)) * 2 * HOUR;
  for (let t = first; t <= x1; t += 2 * HOUR) {
    el("text", { x: sx(t), y: H - 6, "text-anchor": "middle" }, svg).textContent = hm(t);
  }

  if (highlight) {
    const a = Math.max(highlight.start, x0), b = Math.min(highlight.end, x1);
    if (b > a) {
      const g = el("g", { class: "hl" }, svg);
      el("rect", { x: sx(a), y: m.t, width: sx(b) - sx(a), height: H - m.t - m.b, rx: 4 }, g);
      el("text", { x: sx(a) + 6, y: m.t + 14 }, g).textContent = highlight.label;
    }
  }

  if (band && band.upper.length) {
    const top = band.upper.map(([t, v]) => `${sx(t)},${sy(v)}`);
    const bottom = band.lower.slice().reverse().map(([t, v]) => `${sx(t)},${sy(v)}`);
    el("polygon", { points: [...top, ...bottom].join(" "), fill: "var(--band)" }, svg);
  }
  for (const s of series) {
    let d = "", pen = false;
    for (const [t, v] of s.points) {
      if (v === null || Number.isNaN(v)) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${sx(t).toFixed(1)},${sy(v).toFixed(1)}`;
      pen = true;
    }
    el("path", { d, fill: "none", stroke: s.color, "stroke-width": s.width || 2, "stroke-linejoin": "round",
                 "stroke-dasharray": s.dash || "none" }, svg);
  }
  if (nowT !== null) {
    el("line", { x1: sx(nowT), x2: sx(nowT), y1: m.t, y2: H - m.b, class: "now-line" }, svg);
    el("text", { x: sx(nowT) + 4, y: m.t + 10 }, svg).textContent = "now";
  }
}

function renderCharts() {
  if (!state.forecast) return;
  const origin = state.origin;
  const steps = state.forecast.steps.map((s) => ({ ...s, t: Date.parse(s.delivery_start_utc) }));
  const actual = state.actuals.points.map((p) => [Date.parse(p.delivery_start_utc), p.imbalance_price]);
  const end = origin + 10 * HOUR;
  const values = [...actual.map(([, v]) => v), ...steps.flatMap((s) => [s.p10, s.p90])].filter((v) => v !== null);
  let lo = Math.min(...values), hi = Math.max(...values);
  const pad = (hi - lo) * 0.08 || 10;
  lo -= pad; hi += pad;
  drawChart($("price-chart"), {
    x0: state.asOf - LOOKBACK, x1: end, yMin: lo, yMax: hi, yFmt: (v) => `${Math.round(v)}`,
    nowT: state.asOf, highlight: state.highlight,
    band: { upper: steps.map((s) => [s.t, s.p90]), lower: steps.map((s) => [s.t, s.p10]) },
    series: [
      { points: actual, color: "var(--actual)", width: 1.6 },
      { points: steps.map((s) => [s.t, s.p50]), color: "var(--p50)", width: 2.2 },
    ],
  });
  drawChart($("risk-chart"), {
    x0: origin, x1: end, yMin: 0, yMax: 1, yFmt: (v) => `${Math.round(v * 100)}%`, highlight: state.highlight,
    series: [
      { points: steps.map((s) => [s.t, s.p_up]), color: "var(--up)", width: 1.6, dash: "4 3" },
      { points: steps.map((s) => [s.t, s.p_spike_high]), color: "var(--hi)" },
      { points: steps.map((s) => [s.t, s.p_spike_low]), color: "var(--lo)" },
    ],
  });
}

function setHighlight(note, msgNode) {
  state.highlight = note ? { start: Date.parse(note.window_start_utc), end: Date.parse(note.window_end_utc),
                             label: `${note.title} · ${pct(note.probability)}` } : null;
  if (state.activeMsg) state.activeMsg.classList.remove("active");
  state.activeMsg = msgNode || null;
  if (msgNode) msgNode.classList.add("active");
  renderCharts();
}

// ---------- chat ----------
function post(kind, html, extraClass = "") {
  const li = document.createElement("li");
  li.className = `msg ${kind} ${extraClass}`.trim();
  li.innerHTML = html;
  $("messages").appendChild(li);
  li.scrollIntoView({ block: "end", behavior: "smooth" });
  return li;
}

function probBar(n) {
  return `<div class="bar-prob" title="Point: probability. Shaded: calibration range. Tick: usual rate.">
    <span class="range" style="left:${n.probability_low * 100}%;width:${Math.max((n.probability_high - n.probability_low) * 100, 0.5)}%"></span>
    <span class="base" style="left:${n.base_rate * 100}%"></span>
    <span class="point" style="left:calc(${n.probability * 100}% - 1px)"></span></div>`;
}

function postNote(n, how) {
  const verb = { new: "Heads-up", rising: "Rising", eased: "Eased" }[how];
  const sev = how === "eased" ? "eased" : (SEVERITY[n.event] || "");
  const span = `${hm(n.window_start_utc)}–${hm(n.window_end_utc)}`;
  const body = how === "eased"
    ? `<p>Now ${pct(n.probability)}, below the ${pct(chatBar(n))} bar. Nothing to check for ${esc(n.window_label)}.</p>`
    : `<p><strong>${pct(n.probability)}</strong> chance ${esc(n.window_label)} (${span}); model range
         ${pctRange(n.probability_low, n.probability_high)}. That is ${n.lift.toFixed(1)}× the usual ${pct(n.base_rate)}.</p>
       ${probBar(n)}
       <div class="chips"><span class="chip prob">${pct(n.probability)}</span>
         <span class="chip conf-${n.confidence}">${n.confidence} confidence</span>
         <span class="chip">${n.lift.toFixed(1)}× normal</span>
         ${n.low_skill ? '<span class="chip conf-low">low skill</span>' : ""}</div>
       ${n.drivers.length ? `<p>Mostly because of: ${esc(listText(n.drivers.map((d) => d.toLowerCase())))}.</p>` : ""}
       <p>Worth checking ${esc(n.check)}.</p>`;
  const li = post("alert", `<div class="time">${hm(state.asOf)} · ${verb}</div>
      <div class="title">${esc(n.title)} · ${esc(n.window_label)}</div>${body}
      <div class="actions"><button data-act="show">Show on chart</button><button data-act="why">Why?</button></div>`, sev);
  li.querySelector('[data-act="show"]').onclick = () => setHighlight(n, li);
  li.querySelector('[data-act="why"]').onclick = () => explain(n);
  li.onmouseenter = () => { if (!state.activeMsg) setHighlight(n); };
  li.onmouseleave = () => { if (!state.activeMsg) setHighlight(null); };
  if (state.notify && document.hidden && how !== "eased" && "Notification" in window) {
    new Notification(`${n.title} · ${n.window_label}`, { body: `${pct(n.probability)} (${n.confidence} confidence)` });
  }
  return li;
}

function explain(n) {
  post("bot", `<div class="title">Why: ${esc(n.title)}</div>
    <p>The event: ${esc(n.definition)}, ${esc(n.window_label)}.</p>
    <p>In training it happened in ${pct(n.base_rate)} of such windows. I speak up at ${pct(chatBar(n))}
       (twice the usual rate, at least 30 %); now it is ${pct(n.probability)}.</p>
    <p>The range ${pctRange(n.probability_low, n.probability_high)} is the calibration interval: narrow when many
       similar past cases exist. Confidence is <strong>${n.confidence}</strong>: ${CONFIDENCE_TEXT[n.confidence]}.</p>
    ${n.drivers.length ? `<p>Inputs pushing it up: ${esc(listText(n.drivers))}.</p>` : ""}
    ${n.low_skill ? "<p>This event showed little skill on validation; take it as a weak hint.</p>" : ""}`);
}

function summary() {
  const firing = state.notes.filter(loud);
  if (!firing.length) {
    post("bot", `<p>At ${hm(state.asOf)} nothing stands out: no event is above its bar in the next 10 hours.</p>`);
    return;
  }
  const items = firing.map((n) => `<li>${esc(n.title)}, ${esc(n.window_label)}: <strong>${pct(n.probability)}</strong>
     <span class="chip conf-${n.confidence}">${n.confidence}</span></li>`).join("");
  post("bot", `<p>At ${hm(state.asOf)}, ${firing.length} thing${firing.length > 1 ? "s" : ""} worth noting:</p><ul>${items}</ul>`);
}

function diffNotes(reset) {
  if (reset) state.seen.clear();
  const posted = [];
  const queue = [];
  for (const n of state.notes) {
    const key = `${n.event}|${n.window}`;
    const prev = state.seen.get(key);
    const on = loud(n);
    if (on && (!prev || !prev.on)) queue.push([n, "new"]);
    else if (on && prev && n.probability - prev.p >= RISE) queue.push([n, "rising"]);
    else if (!on && prev && prev.on) queue.push([n, "eased"]);
    state.seen.set(key, { p: n.probability, on });
  }
  const urgent = queue.filter(([, how]) => how !== "eased");
  const eased = queue.filter(([, how]) => how === "eased");
  for (const [n, how] of urgent.slice(0, MAX_NEW_PER_UPDATE)) posted.push([n, postNote(n, how)]);
  if (urgent.length > MAX_NEW_PER_UPDATE) {
    post("system", `…and ${urgent.length - MAX_NEW_PER_UPDATE} more. Ask “what's going on?” for the full list.`);
  }
  if (eased.length) {
    post("alert", `<div class="time">${hm(state.asOf)} · Eased</div>
      <p>${esc(listText(eased.map(([n]) => `${n.title.toLowerCase()} (${n.window_label})`)))} dropped below the bar.</p>`, "eased");
  }
  if (posted.length) setHighlight(posted[0][0], posted[0][1]);      // spotlight the most important new note
  else if (reset) setHighlight(null);
}

// ---------- ask box (a tiny local responder, no language model) ----------
function answer(text) {
  const q = text.toLowerCase();
  if (/clear|reset|hide/.test(q)) { setHighlight(null); post("bot", "<p>Highlight cleared.</p>"); return; }
  if (/(next|forward|later)\b/.test(q) && /hour|step/.test(q)) { step(+1); return; }
  if (/(back|previous|earlier)\b/.test(q) && /hour|step/.test(q)) { step(-1); return; }
  if (/why|explain|how sure|uncertain/.test(q)) {
    const match = state.notes.find((n) => n.event.split("_").every((w) => q.includes(w)))
      || state.notes.find((n) => n.title.toLowerCase().split(" ").filter((w) => w.length > 3 && q.includes(w)).length >= 2)
      || state.notes.find(loud);
    if (match) { explain(match); setHighlight(match); return; }
  }
  if (/what|going on|status|summary|anything/.test(q)) { summary(); return; }
  post("bot", `<p>I can summarise (“what's going on?”), explain a note (“why spike high?”), step time
    (“next hour”) or clear the highlight. I only know what the forecasts and classifiers say.</p>`);
}

// ---------- time ----------
function clampOrigin(t) {
  const first = Date.parse(state.meta.first_origin_utc), last = Date.parse(state.meta.last_origin_utc);
  return Math.min(Math.max(t, first), last);
}

async function load(asOf, { reset = false } = {}) {
  const t = clampOrigin(asOf);
  const at = iso(t);
  try {
    const [forecast, actuals, notes] = await Promise.all([
      api("forecast", { as_of: at }),
      api("actuals", { as_of: at, from: iso(t - LOOKBACK) }),
      api("notes", { as_of: at }),
    ]);
    const jump = state.asOf === null || Math.abs(t - state.asOf) !== HOUR;
    Object.assign(state, { asOf: t, origin: Date.parse(forecast.origin_utc), forecast, actuals, notes: notes.notes });
    $("now-text").textContent = dateFmt.format(new Date(t));
    if (reset || jump) {
      post("system", `Viewing ${dateFmt.format(new Date(t))} · forecast ${forecast.model}, notes ${notes.model}`);
    }
    renderCharts();
    diffNotes(reset || jump);
    if ((reset || jump) && !state.notes.some(loud)) summary();
  } catch (err) {
    post("system", `Could not load data: ${esc(err.message)}`);
  }
}

const step = (hours) => load(state.asOf + hours * HOUR);

function togglePlay() {
  if (state.timer) {
    clearInterval(state.timer); state.timer = null; $("play").textContent = "Replay"; return;
  }
  $("play").textContent = "Pause";
  state.timer = setInterval(() => {
    if (state.asOf >= Date.parse(state.meta.last_origin_utc)) { togglePlay(); return; }
    step(+1);
  }, 1800);
}

async function init() {
  try {
    state.meta = await api("meta");
  } catch (err) {
    $("mode-note").textContent = "API not reachable. Start it with: uv run uvicorn backend.api.main:app";
    post("system", esc(err.message));
    return;
  }
  $("mode-note").textContent = `${state.meta.mode === "mock" ? "Mock data" : "Backtest"} · ${state.meta.note}`;
  post("bot", `<p>Hi! I watch the imbalance price forecast and the event classifiers, and I post here when
    something is worth noting in the next 10 hours, with how sure the model is. Press <strong>Replay</strong> to
    step through time, or ask me something.</p>`);
  $("prev").onclick = () => step(-1);
  $("next").onclick = () => step(+1);
  $("play").onclick = togglePlay;
  $("jump").onchange = (e) => { if (e.target.value) load(new Date(e.target.value).getTime(), { reset: true }); };
  $("ask").onsubmit = (e) => {
    e.preventDefault();
    const text = $("question").value.trim();
    if (!text) return;
    post("user", `<p>${esc(text)}</p>`);
    $("question").value = "";
    answer(text);
  };
  $("notify").onclick = async () => {
    if (!("Notification" in window)) { post("system", "This browser has no desktop notifications."); return; }
    state.notify = (await Notification.requestPermission()) === "granted";
    $("notify").textContent = state.notify ? "Alerts on" : "Enable alerts";
  };
  window.addEventListener("resize", renderCharts);
  const start = Date.parse(state.meta.last_origin_utc) - 48 * HOUR;   // leave room to replay forward
  await load(Math.floor(start / HOUR) * HOUR, { reset: true });
}

init();
