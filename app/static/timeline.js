// app/static/timeline.js — the backend as a live timeline: where the file is and which real check ran, with server times.
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const STAGES = [
  ["pc", "This computer", "the document is picked or photographed"],
  ["vm", "Vultr server", "Cloud Compute VM receives the image"],
  ["ai", "Vultr Serverless Inference", "two AI readers read it at the same time"],
  ["compare", "Compare", "do both readers agree, field by field?"],
  ["check", "Checks", "fixed rules, no AI"],
  ["chain", "Audit trail", "the result is chained with a hash"],
];

export function resetTimeline(what) {
  $("#tl").innerHTML = STAGES.map(([k, t, sub]) => `<li class="tl-node" data-k="${k}"><span class="tl-dot"></span>
    <div><b>${t}</b> <span class="tl-ms"></span><br><small class="muted">${sub}</small><ul class="tl-rows"></ul></div></li>`).join("");
  node("pc", "on", what, 0, true);
  { const ai = $('.tl-node[data-k="ai"] .tl-rows');
    ai.innerHTML = `<li id="lane0" class="lane">Reader 1 <span class="muted">glm-5.3-flash</span>: waiting</li><li id="lane1" class="lane">Reader 2 <span class="muted">qwen3.8-27b</span>: waiting</li>`; }
}

function node(k, cls, text, ms, ok) {
  const n = $(`.tl-node[data-k="${k}"]`); if (!n) return;
  n.classList.add(cls); if (ms !== undefined && !n.querySelector(".tl-ms").textContent) n.querySelector(".tl-ms").textContent = `+${(ms / 1000).toFixed(2)} s`;
  if (text) { const li = document.createElement("li"); li.className = ok ? "ok" : "bad"; li.textContent = text; n.querySelector(".tl-rows").appendChild(li); }
}

// Vultr's own receipt for the call: its request id, its clock, the model it says answered
const vultr = v => v && v.id ? `<span class="vx"><b>Vultr receipt</b> <code>${esc(v.id)}</code> <span>${esc(v.model)} · Vultr clock ${new Date(v.created * 1000).toISOString().slice(11, 19)} UTC</span></span>` : "";

export function applyStep(s) {
  // s = {key, ms, text, ok, fields?} straight from the server job
  if (s.key === "vm") { node("pc", "done"); node("vm", "on", s.text, s.ms, true); }
  else if (s.key.startsWith("send")) { node("vm", "done"); node("ai", "on", null, s.ms);
    const lane = $(`#lane${s.key.slice(-1)}`); lane.classList.add("busy"); lane.innerHTML = lane.innerHTML.replace("waiting", "reading…"); }
  else if (s.key.startsWith("read")) { const lane = $(`#lane${s.key.slice(-1)}`); lane.classList.remove("busy"); lane.classList.add(s.ok ? "ok" : "bad");
    const f = s.fields || {}; lane.innerHTML = `${esc(s.text)}${f.supplier ? `<br><small>read: ${esc(f.supplier)} · ${esc(f.invoice_no)} · ${esc(f.total)} · due ${esc(f.due_date)}</small>` : ""}${vultr(s.vultr)}`; }
  else if (s.key === "compare") { node("ai", "done"); node("compare", s.ok ? "done" : "warn", s.text, s.ms, s.ok); }
  else if (s.key === "check") { node("compare", s.ok ? "done" : "warn"); node("check", "on", s.text, s.ms, s.ok); }
  else if (s.key === "chain") { node("check", "done"); node("chain", "done", s.text, s.ms, true); }
  else if (s.key === "error") { document.querySelectorAll(".tl-node.on").forEach(n => n.classList.add("fail")); node("chain", "fail", s.text, s.ms, false); }
}
