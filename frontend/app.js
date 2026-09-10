/* LLD Coach SPA — vanilla JS, no build step. */
const $ = (s) => document.querySelector(s);
const state = { problems: [], currentAttempt: null, currentProblem: null, pollTimer: null };

const SECTIONS = [
  ["assumptions", "Assumptions", "What ambiguous requirements did you assume? (e.g. capacity, concurrency, payment modes)"],
  ["class_definitions", "Classes / Interfaces", "One line per class: name + responsibility. Mark interfaces/abstract. e.g. class ParkingSpot { ... }"],
  ["relationships", "Relationships", "Composition vs aggregation vs dependency + multiplicity. e.g. ParkingFloor *— ParkingSpot (1..*)"],
  ["behaviors", "Methods / Behavior", "Key flows: entry→allocate→ticket, exit→fee→free. Who calls whom?"],
  ["design_decisions", "Design Decisions", "Why these abstractions? Which alternatives did you reject?"],
  ["tradeoffs", "Trade-offs", "What did you sacrifice (simplicity vs extensibility, memory vs speed)?"],
  ["edge_cases", "Edge Cases", "Full lot, invalid ticket, concurrency, payment failure, restock mid-txn..."],
];

const SAMPLES = {
  "parking-lot": {
    assumptions: "3 floors x 50 spots. Bike fits Small+, Car fits Compact+, Truck needs Large. Hourly billing, 15-min grace. Single entry/exit gate per floor, concurrent entries possible so allocation must be thread-safe.",
    class_definitions: "class Vehicle { plate; type: Bike|Car|Truck; size() }\nclass ParkingSpot { id; size: Small|Compact|Large; occupied: bool; vehicle? }\nclass ParkingFloor { floorNo; spots: ParkingSpot[]; freeCount(size) }\ninterface SpotAllocationStrategy { allocate(vehicle, floors): ParkingSpot? } class SmallestFitStrategy implements SpotAllocationStrategy\nclass Ticket { id; vehicle; spotId; entryTime }\ninterface PricingStrategy { fee(ticket, exitTime): Money } class HourlyPricing implements PricingStrategy; class WeekendSurchargeDecorator implements PricingStrategy\nclass ParkingLot { floors; allocation: SpotAllocationStrategy; pricing: PricingStrategy; enter(v): Ticket; exit(ticketId): Money }\nclass Gate { lot: ParkingLot }",
    relationships: "ParkingLot *— ParkingFloor (1..* composition, lot owns floors). ParkingFloor *— ParkingSpot (1..* composition). Ticket → Vehicle, Ticket → ParkingSpot (association, references by id). ParkingLot → SpotAllocationStrategy (dependency, injected). ParkingLot → PricingStrategy (dependency, injected). SmallestFitStrategy ..|> SpotAllocationStrategy. HourlyPricing ..|> PricingStrategy.",
    behaviors: "enter(vehicle): strategy.allocate smallest fitting free spot; mark occupied; create Ticket(entryTime). exit(ticketId): lookup ticket; fee = pricing.fee(ticket, now); free spot; return receipt. Full lot: allocate returns null -> entry rejected with message. Pricing.fee isolated so it can be unit-tested with fake tickets.",
    design_decisions: "Strategy for allocation and pricing because both vary independently (new vehicle type, new fee rules). Chose composition over inheritance for vehicle sizes (size() method, not subclasses) to avoid class explosion. Ticket references spot by id to keep exit lookup O(1). Rejected Singleton for ParkingLot to keep tests isolated; use one instance in main.",
    tradeoffs: "Smallest-fit scan is O(spots) per entry — simple and fine for hundreds of spots; would index free spots by size if 10k+. Storing exit-time computation in PricingStrategy duplicates duration logic per strategy, accepted for independence. No persistence layer in LLD scope; assumed in-memory with repository seam later.",
    edge_cases: "Full lot -> reject with retry message. Duplicate entry same plate -> reject if active ticket exists. Invalid/expired ticket on exit -> error, spot stays occupied. Concurrent entries racing for last spot -> allocate under lock; loser gets full-lot message. Clock skew on exit before entry -> clamp to grace minimum. Lost ticket -> lookup by plate with operator override."
  },
  "elevator-system": {
    assumptions: "8 floors, 3 elevators, max 10 persons each. SCAN dispatch default. Door obstruction sensor available. Requests are idempotent (repeated hall press = one request).",
    class_definitions: "class Request { floor; direction: Up|Down; source: Hall|Cabin }\nclass Elevator { id; currentFloor; state: Idle|MovingUp|MovingDown|DoorsOpen|Overloaded; capacity; passengers; moveTo(f); openDoors(); closeDoors() }\ninterface DispatchStrategy { pick(request, elevators): Elevator } class ScanDispatch implements DispatchStrategy; class NearestDispatch implements DispatchStrategy\nclass Dispatcher { strategy: DispatchStrategy; assign(request) }\nclass Building { elevators: Elevator[]; dispatcher: Dispatcher; pressHallButton(); pressCabinButton() }",
    relationships: "Building *— Elevator (1..* composition). Building → Dispatcher (owns). Dispatcher → DispatchStrategy (injected dependency). ScanDispatch ..|> DispatchStrategy. Request → Elevator (association after assignment). Elevator state transitions explicit via state field, not scattered booleans.",
    behaviors: "pressHallButton(floor, dir): create Request; dispatcher.assign picks elevator via strategy; elevator queues target. Elevator loop: move toward next target in scan order; on arrival openDoors, timeout closeDoors; obstruction -> reopen + timer reset. Overload sensor -> state Overloaded, doors stay open, refuse move. Swapping ScanDispatch for NearestDispatch needs no Elevator edits.",
    design_decisions: "Separated movement (Elevator) from dispatch (Dispatcher+Strategy) so scheduling changes don't touch motion code. State as explicit enum for testability. Strategy pattern for dispatch because building wants A/B of algorithms. Rejected per-elevator queues owned by Dispatcher centrally to avoid double-dispatch.",
    tradeoffs: "SCAN is fair but slower for sparse traffic vs nearest; accepted, strategy swappable. Central dispatcher is a single contention point — fine for 3 elevators, would shard by zone at 20+. Door timeout fixed 5s; configurable later.",
    edge_cases: "All requests same direction -> SCAN still sweeps, no starvation. Power-out -> elevators stop, requests persist in dispatcher queue, resume on power. Stuck door -> after 3 retries mark out-of-service, reassign its queue. Overload -> refuse close, alarm. Duplicate hall press -> dedupe by (floor, direction)."
  },
  "vending-machine": {
    assumptions: "20 slots, coins {1,2,5,10} + notes {10,20,50}. Exact-change mode possible. One dispense at a time. Operator restocks daily.",
    class_definitions: "class Product { code; name; price; qty }\nclass Inventory { slots: map<code,Product>; get(code); decrement(code); restock(code, n); isEmpty(code) }\ninterface PaymentMethod { insert(amount); refundable(): Money; charge(price): Change } class CashPayment implements PaymentMethod { inserted; coinBox } class CardPayment implements PaymentMethod\nclass Dispenser { inventory: Inventory; dispense(code) }\nclass VendingMachine { state: Idle|AcceptingMoney|Dispensing|OutOfService; inventory; payment: PaymentMethod; dispenser; select(code); insertMoney(a); cancel(): refund; collectCash() }",
    relationships: "VendingMachine *— Inventory (composition). VendingMachine → PaymentMethod (injected; CashPayment or CardPayment). VendingMachine → Dispenser (owns). Dispenser → Inventory (uses). CashPayment owns coinBox for change computation. State enum drives allowed transitions.",
    behaviors: "select(code): if out-of-stock -> message + stay Idle; else state=AcceptingMoney. insertMoney: accumulate; when inserted>=price -> state=Dispensing, dispense, return change, state=Idle. cancel(): refund inserted, state=Idle. Exact-change-only: if coinBox can't make change -> reject large notes upfront. Adding CardPayment needs no Dispenser edits.",
    design_decisions: "PaymentMethod interface so card/mobile plugs in without touching dispense. Inventory separate from money so stock and cash evolve independently. Explicit state enum prevents illegal moves (e.g. dispense while Idle). Rejected inheritance for products (just data) to avoid over-engineering.",
    tradeoffs: "Greedy change-making is optimal for canonical coin set; documented assumption, replaceable. Single-dispense lock simplifies concurrency but limits throughput — fine for one machine. In-memory inventory; persistence seam via repository later.",
    edge_cases: "Insufficient funds -> show remaining, allow top-up or cancel+refund. Sold-out after payment -> auto-refund. Jammed dispenser -> refund + OutOfService, operator alert. Invalid code -> error, money retained for next selection. Power loss mid-dispense -> on boot reconcile: if paid and not dispensed, refund."
  }
};

function showAlert(msg, kind = "error") {
  const el = $("#alert");
  el.className = "mb-4 p-3 rounded-xl text-sm " + (kind === "error" ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(showAlert._t);
  showAlert._t = setTimeout(() => el.classList.add("hidden"), 6000);
}

function show(view) {
  for (const v of ["library", "detail", "practice", "feedback", "history"])
    $("#view-" + v).classList.toggle("hidden", v !== view);
  window.scrollTo({ top: 0 });
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) throw new Error((data && (data.detail || data.message)) || `HTTP ${res.status}`);
  return data;
}

// ---------- Library ----------
async function loadProblems() {
  const problems = await api("/api/problems");
  state.problems = problems;
  const cards = $("#problemCards");
  cards.innerHTML = "";
  const filt = $("#historyFilter");
  filt.innerHTML = '<option value="">All problems</option>';
  for (const p of problems) {
    filt.innerHTML += `<option value="${p.id}">${p.title}</option>`;
    const div = document.createElement("div");
    div.className = "bg-white rounded-2xl border p-5 flex flex-col";
    div.innerHTML = `
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-bold px-2 py-1 rounded-full ${p.difficulty === "Beginner" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}">${p.difficulty}</span>
        <span class="text-xs text-slate-500">~${p.estimated_minutes} min</span>
      </div>
      <h2 class="font-bold text-lg">${p.title}</h2>
      <p class="text-sm text-slate-600 mt-1 flex-1">${p.description.slice(0, 160)}...</p>
      <div class="text-xs text-slate-500 mt-2">${p.requirements.length} requirements · ${p.evaluation_criteria.length} rubric criteria</div>
      <div class="flex gap-2 mt-3">
        <button class="flex-1 px-3 py-2 rounded-xl bg-slate-900 text-white text-sm hover:bg-slate-700" data-open="${p.id}">Open</button>
        <button class="flex-1 px-3 py-2 rounded-xl bg-emerald-600 text-white text-sm hover:bg-emerald-700" data-practice="${p.id}">Practice →</button>
      </div>`;
    cards.appendChild(div);
  }
  cards.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openProblem(b.dataset.open));
  cards.querySelectorAll("[data-practice]").forEach(b => b.onclick = () => startAttempt(b.dataset.practice));
}

async function openProblem(id) {
  const p = await api(`/api/problems/${id}`);
  state.currentProblem = p;
  $("#problemDetail").innerHTML = `
    <div class="bg-white rounded-2xl border p-6">
      <div class="flex items-center gap-2 mb-1">
        <h1 class="text-2xl font-bold">${p.title}</h1>
        <span class="text-xs font-bold px-2 py-1 rounded-full bg-slate-200">${p.difficulty}</span>
        <span class="text-xs text-slate-500">~${p.estimated_minutes} min</span>
      </div>
      <p class="text-slate-700 mt-2">${p.description}</p>
      <div class="grid md:grid-cols-2 gap-4 mt-4">
        <div class="bg-slate-50 rounded-xl p-4">
          <h3 class="font-bold text-sm mb-2">Requirements</h3>
          <ul class="text-sm list-disc ml-5 space-y-1">${p.requirements.map(r => `<li>${r}</li>`).join("")}</ul>
        </div>
        <div class="bg-slate-50 rounded-xl p-4">
          <h3 class="font-bold text-sm mb-2">Constraints</h3>
          <ul class="text-sm list-disc ml-5 space-y-1">${p.constraints.map(r => `<li>${r}</li>`).join("")}</ul>
        </div>
      </div>
      <div class="mt-4 bg-slate-50 rounded-xl p-4">
        <h3 class="font-bold text-sm mb-2">How you are evaluated (rubric, 100 pts)</h3>
        <div class="flex flex-wrap gap-2">${p.evaluation_criteria.map(c => `<span class="text-xs px-2 py-1 rounded-full bg-white border">${c.name} · ${c.weight}</span>`).join("")}</div>
      </div>
      <button id="btnStartFromDetail" class="mt-4 px-5 py-2.5 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700">Start Attempt →</button>
    </div>`;
  $("#btnStartFromDetail").onclick = () => startAttempt(p.id);
  show("detail");
}

// ---------- Attempts ----------
async function startAttempt(problemId) {
  try {
    const a = await api(`/api/problems/${problemId}/attempts`, { method: "POST" });
    await openAttempt(a.id);
  } catch (e) { showAlert(e.message); }
}

function editorValues() {
  const out = {};
  for (const [key] of SECTIONS) out[key] = $("#f_" + key).value;
  return out;
}
function setEditorValues(sub) {
  for (const [key] of SECTIONS) $("#f_" + key).value = (sub && sub[key]) || "";
}

async function openAttempt(id) {
  clearInterval(state.pollTimer);
  const a = await api(`/api/attempts/${id}`);
  state.currentAttempt = a;
  const p = state.problems.find(x => x.id === a.problem_id) || await api(`/api/problems/${a.problem_id}`);
  state.currentProblem = p;
  $("#practiceTitle").textContent = `${p.title} — Attempt ${a.id.slice(-6)}`;
  const grid = $("#editorGrid");
  grid.innerHTML = "";
  for (const [key, label, hint] of SECTIONS) {
    const wrap = document.createElement("div");
    wrap.className = "field bg-white rounded-2xl border p-4";
    wrap.innerHTML = `<label class="font-bold text-sm">${label}</label>
      <div class="text-xs text-slate-500 mb-2">${hint}</div>
      <textarea id="f_${key}" class="w-full border rounded-xl p-3 text-sm font-mono" placeholder="Write your ${label.toLowerCase()}..."></textarea>`;
    grid.appendChild(wrap);
  }
  setEditorValues(a.submission);
  renderAttemptMeta(a);
  show("practice");
}

function renderAttemptMeta(a) {
  const pill = `<span class="status-pill st-${a.status}">${a.status}</span>`;
  $("#attemptMeta").innerHTML = `Attempt <b>${a.id}</b> · ${pill} · started ${new Date(a.created_at).toLocaleString()}`;
  const box = $("#evalStatus");
  if (a.status === "COMPLETED" && a.evaluation) {
    box.innerHTML = `<div class="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-sm">✓ Evaluated — score <b>${a.evaluation.overall_score}/100</b> (${a.evaluation.provider}). <button id="btnViewFb" class="ml-2 px-3 py-1 rounded-lg bg-emerald-600 text-white">View feedback →</button></div>`;
    $("#btnViewFb").onclick = () => openFeedback(a.id);
  } else if (a.status === "FAILED") {
    const err = a.evaluation?.error || "Evaluation failed.";
    box.innerHTML = `<div class="p-3 rounded-xl bg-red-50 border border-red-200 text-sm">✗ Evaluation <b>FAILED</b> — submission preserved. <span class="text-slate-600">${err}</span> <button id="btnRetryEv" class="ml-2 px-3 py-1 rounded-lg bg-slate-900 text-white">Retry evaluation</button></div>`;
    $("#btnRetryEv").onclick = retryEvaluation;
  } else if (a.status === "EVALUATING" || a.status === "SUBMITTED") {
    box.innerHTML = `<div class="p-3 rounded-xl bg-amber-50 border border-amber-200 text-sm"><span class="spin"></span> Evaluation in progress (${a.status}) — safe to wait or refresh; submission is stored.</div>`;
  } else {
    box.innerHTML = `<div class="p-3 rounded-xl bg-slate-100 text-sm text-slate-600">Draft — save anytime, submit when all 7 sections are substantive.</div>`;
  }
}

async function saveDraft() {
  const a = state.currentAttempt;
  try {
    const updated = await api(`/api/attempts/${a.id}`, { method: "PUT", body: JSON.stringify(editorValues()) });
    state.currentAttempt = updated;
    renderAttemptMeta(updated);
    showAlert("Draft saved.", "ok");
  } catch (e) { showAlert(e.message); }
}

async function submitAttempt() {
  const a = state.currentAttempt;
  $("#btnSubmit").disabled = true;
  $("#evalStatus").innerHTML = `<div class="p-3 rounded-xl bg-amber-50 border text-sm"><span class="spin"></span> Submitting + evaluating… (deterministic checks, then rubric AI)</div>`;
  try {
    const updated = await api(`/api/attempts/${a.id}/submit`, { method: "POST", body: JSON.stringify(editorValues()) });
    state.currentAttempt = updated;
    renderAttemptMeta(updated);
    if (updated.status === "COMPLETED") openFeedback(updated.id);
    else if (updated.status === "FAILED") showAlert("Evaluation failed — submission preserved. Use Retry evaluation.", "error");
    else pollUntilDone(updated.id);
  } catch (e) { showAlert(e.message); }
  finally { $("#btnSubmit").disabled = false; }
}

async function pollUntilDone(id, tries = 0) {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      const a = await api(`/api/attempts/${id}`);
      state.currentAttempt = a;
      renderAttemptMeta(a);
      if (a.status === "COMPLETED") { clearInterval(state.pollTimer); openFeedback(id); }
      if (a.status === "FAILED") clearInterval(state.pollTimer);
    } catch {}
    if (++tries > 40) clearInterval(state.pollTimer);
  }, 2500);
}

async function retryEvaluation() {
  const a = state.currentAttempt;
  try {
    const updated = await api(`/api/attempts/${a.id}/retry-evaluation`, { method: "POST" });
    state.currentAttempt = updated;
    renderAttemptMeta(updated);
    if (updated.status === "COMPLETED") openFeedback(updated.id);
  } catch (e) { showAlert(e.message); }
}

// ---------- Feedback ----------
function sevColor(s) { return s === "high" ? "bg-red-100 text-red-800" : s === "low" ? "bg-slate-200 text-slate-700" : "bg-amber-100 text-amber-800"; }

async function openFeedback(attemptId) {
  const a = await api(`/api/attempts/${attemptId}`);
  const ev = a.evaluation;
  if (!ev) { showAlert("No evaluation yet."); return; }
  const p = state.problems.find(x => x.id === a.problem_id) || state.currentProblem;
  let html = "";
  if (ev.status === "FAILED") {
    html = `<div class="bg-white rounded-2xl border p-6">
      <h1 class="text-xl font-bold">Evaluation failed — nothing lost</h1>
      <p class="text-sm text-slate-600 mt-1">Your submission is stored. Error: ${ev.error || "unknown"}</p>
      <div class="flex gap-2 mt-4">
        <button id="fbRetry" class="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm">Retry evaluation</button>
        <button id="fbBack" class="px-4 py-2 rounded-xl bg-slate-200 text-sm">Back to editor</button>
      </div></div>`;
    $("#feedbackBody").innerHTML = html;
    $("#fbRetry").onclick = async () => { state.currentAttempt = a; await retryEvaluation(); };
    $("#fbBack").onclick = () => openAttempt(a.id);
    show("feedback");
    return;
  }
  const crit = (ev.criterion_results || []).map(c => `
    <div class="bg-slate-50 rounded-xl p-3">
      <div class="flex justify-between text-sm"><b>${c.name}</b><span>${c.score}/${c.max_score}</span></div>
      <div class="scorebar mt-1"><div style="width:${Math.round(100 * c.score / Math.max(1, c.max_score))}%"></div></div>
      <div class="text-xs mt-2"><b class="text-emerald-700">Evidence:</b> ${c.evidence || "—"}</div>
      <div class="text-xs mt-1"><b class="text-red-700">Concern:</b> ${c.concern || "—"}</div>
      <div class="text-xs mt-1"><b>Suggestion:</b> ${c.suggestion || "—"} <span class="text-slate-400">(conf ${c.confidence ?? "?"})</span></div>
    </div>`).join("");
  const det = ev.deterministic || {};
  const detChecks = (det.checks || []).map(c => `<li class="${c.passed ? "text-emerald-700" : "text-red-700"}">${c.passed ? "✓" : "✗"} <b>${c.check}</b> — ${c.detail}</li>`).join("");
  const impr = (ev.improvements || []).map(i => {
    if (typeof i === "string") return `<li>${i}</li>`;
    return `<li><span class="text-xs px-2 py-0.5 rounded-full ${sevColor(i.severity)}">${i.severity || "medium"}</span> ${i.message || ""} <span class="text-slate-400 text-xs">[${i.section || ""}]</span></li>`;
  }).join("");
  html = `
  <div class="bg-white rounded-2xl border p-6">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div>
        <h1 class="text-2xl font-bold">${p ? p.title : a.problem_id} — ${ev.overall_score}/100</h1>
        <div class="text-xs text-slate-500">Attempt ${a.id} · ${a.status} · provider: ${ev.provider} · ${new Date(a.created_at).toLocaleString()}</div>
      </div>
      <div class="flex gap-2">
        <button id="fbAgain" class="px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm">Try Again (new attempt)</button>
        <button id="fbEdit" class="px-4 py-2 rounded-xl bg-slate-200 text-sm">Back to editor</button>
      </div>
    </div>
    <div class="scorebar mt-3"><div style="width:${ev.overall_score}%"></div></div>
    <div class="grid md:grid-cols-2 gap-3 mt-4">${crit}</div>
    <div class="grid md:grid-cols-2 gap-4 mt-4">
      <div class="bg-emerald-50 rounded-xl p-4"><h3 class="font-bold text-sm mb-2">Strengths</h3><ul class="text-sm list-disc ml-5 space-y-1">${(ev.strengths || []).map(s => `<li>${s}</li>`).join("")}</ul></div>
      <div class="bg-amber-50 rounded-xl p-4"><h3 class="font-bold text-sm mb-2">Top improvements</h3><ul class="text-sm list-disc ml-5 space-y-1">${impr}</ul></div>
    </div>
    <div class="mt-4 bg-slate-50 rounded-xl p-4">
      <h3 class="font-bold text-sm mb-2">Deterministic checks (no LLM judgment)</h3>
      <ul class="text-sm space-y-1">${detChecks || "<li>—</li>"}</ul>
      <div class="text-xs text-slate-500 mt-2">Deterministic sub-score: ${det.score ?? "?"} · missing: ${(det.missing_sections || []).join(", ") || "none"} · uncovered concepts: ${(det.missing_concepts || []).map(m => m.concept).join(", ") || "none"}</div>
    </div>
    <div class="mt-4 bg-slate-50 rounded-xl p-4">
      <h3 class="font-bold text-sm mb-2">Questions to stretch the design</h3>
      <ul class="text-sm list-disc ml-5 space-y-1">${(ev.next_questions || []).map(q => `<li>${q}</li>`).join("")}</ul>
    </div>
  </div>`;
  $("#feedbackBody").innerHTML = html;
  $("#fbAgain").onclick = async () => {
    const na = await api(`/api/attempts/${a.id}/retry`, { method: "POST" });
    await openAttempt(na.id);
  };
  $("#fbEdit").onclick = () => openAttempt(a.id);
  show("feedback");
}

// ---------- History ----------
async function loadHistory() {
  const f = $("#historyFilter").value;
  const attempts = await api("/api/attempts" + (f ? `?problem_id=${f}` : ""));
  const box = $("#historyList");
  if (!attempts.length) { box.innerHTML = `<div class="bg-white border rounded-2xl p-5 text-sm text-slate-600">No attempts yet. Start from Problems → Practice.</div>`; return; }
  // group trend per problem
  box.innerHTML = "";
  for (const a of attempts) {
    const p = state.problems.find(x => x.id === a.problem_id);
    const score = a.evaluation?.overall_score;
    const div = document.createElement("div");
    div.className = "bg-white border rounded-2xl p-4 flex items-center justify-between flex-wrap gap-2";
    div.innerHTML = `
      <div>
        <div class="font-bold">${p ? p.title : a.problem_id} <span class="status-pill st-${a.status} ml-1">${a.status}</span></div>
        <div class="text-xs text-slate-500">${new Date(a.created_at).toLocaleString()} · ${a.id} ${score != null ? `· <b class="text-slate-800">${score}/100</b> (${a.evaluation.provider})` : ""}</div>
      </div>
      <div class="flex gap-2">
        <button class="px-3 py-1.5 text-sm rounded-xl bg-slate-200" data-open-att="${a.id}">Open</button>
        ${a.status === "COMPLETED" ? `<button class="px-3 py-1.5 text-sm rounded-xl bg-emerald-600 text-white" data-fb="${a.id}">Feedback</button>` : ""}
      </div>`;
    box.appendChild(div);
  }
  box.querySelectorAll("[data-open-att]").forEach(b => b.onclick = () => openAttempt(b.dataset.openAtt));
  box.querySelectorAll("[data-fb]").forEach(b => b.onclick = () => openFeedback(b.dataset.fb));
}

// ---------- wiring ----------
document.querySelectorAll("[data-nav]").forEach(b => b.onclick = () => {
  const v = b.dataset.nav;
  if (v === "history") loadHistory();
  show(v);
});
$("#btnSave").onclick = saveDraft;
$("#btnSubmit").onclick = submitAttempt;
$("#btnSample").onclick = () => {
  const pid = state.currentAttempt?.problem_id;
  const s = SAMPLES[pid];
  if (!s) return showAlert("No sample for this problem.");
  setEditorValues({ class_definitions: s.class_definitions, assumptions: s.assumptions, relationships: s.relationships, behaviors: s.behaviors, design_decisions: s.design_decisions, tradeoffs: s.tradeoffs, edge_cases: s.edge_cases });
  showAlert("Sample loaded — edit it in your own words, then Submit.", "ok");
};
$("#btnRefreshHistory").onclick = loadHistory;
$("#historyFilter").onchange = loadHistory;

(async function init() {
  try {
    await loadProblems();
    $("#providerBadge").textContent = "hybrid eval: deterministic + rubric AI";
    show("library");
  } catch (e) {
    showAlert("Backend unreachable: " + e.message + " — run: python backend/server.py (port 8000) and open http://127.0.0.1:8000/");
  }
})();
