// app/static/stage.js — scan room wiring: pick/capture a document, start the real server job, follow its steps live.
import { createStage } from "/static/stage3d.js";
import { applyStep, resetTimeline } from "/static/timeline.js";
import { talk } from "/static/stage_talk.js";

const $ = s => document.querySelector(s);
let stage = null;
try { stage = createStage($("#scene")); }
catch (e) { $("#scene").innerHTML = '<p class="muted">The 3D view needs WebGL; the server steps still show on the right.</p>'; }
export const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const OK = ["ready", "confirmed"], sleep = ms => new Promise(f => setTimeout(f, ms));
const verdictOf = v => OK.includes(v.status) ? ["ok", v.status === "confirmed" ? "CONFIRMED" : "OK"] : v.status === "confirm" ? ["ask", "CHECK"] : ["bad", "ON HOLD"];

export function showResult(v, receipts = []) {
  const head = v.status === "confirmed" ? "Confirmed by Maria. All checks pass." : (v.headline || v.label);
  const how = v.status === "confirmed" ? "" : v.live ? "Both readers were called live on Vultr for this scan." : "AI is off on this server: saved answers were used.";
  $("#result").innerHTML = `<p class="st-head st-${esc(v.status)}">${esc(head)}</p>
    ${v.why.length && !OK.includes(v.status) ? `<ul class="st-why">${v.why.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}${receipts.length ? `<p class="st-rcpt">Read on Vultr · ${receipts.map(r => `<code>${esc(r.id.slice(0, 22))}…</code>`).join(" · ")}</p>` : ""}<p class="muted small">${how}</p>`;
  const [kind, word] = verdictOf(v);
  if (stage) stage.result(kind, word).then(() => {});
}

const setCount = n => { $("#n").textContent = n; $("#run").disabled = !n; };
const lock = on => document.querySelectorAll(".st-ctl button, .st-ctl input, .rc").forEach(b => b.disabled = on);

async function scan(form, preview, title, sample) {
  lock(true); talk.hide(); resetTimeline(title);
  $("#result").innerHTML = `<p class="st-head">Scanning ${esc(title)}…</p>`;
  try {
    if (stage) { await stage.pick(preview, title); stage.scanning(); setTimeout(() => stage.view("screen"), 700); }
    const res = await fetch("/stage/scan", { method: "POST", body: form }), j = await res.json();
    if (!res.ok) throw new Error(j.error || res.statusText);
    let seen = 0, job; const receipts = [];
    for (let i = 0; i < 400; i++) {  // follow the real job: each step appears when the server reports it
      job = await (await fetch(`/stage/job/${j.job}`)).json();
      for (const s of job.steps.slice(seen)) { applyStep(s); if (s.vultr?.id) receipts.push(s.vultr); }
      seen = job.steps.length;
      if (job.done) break;
      await sleep(250);
    }
    if (!job.v) throw new Error(job.steps.at(-1)?.text || "no result");
    const v = job.v; showResult(v, receipts); setCount(v.scanned); talk.start(v);
    if (sample) { const g = $(`#got-${sample}`), good = OK.includes(v.status);
      const later = g.closest(".rc").dataset.later && good;  // passes the scan on purpose: the bank match or payment check catches it
      g.textContent = later ? "Server: passed the scan ✓ as expected (caught at the bank match)"
        : `Server: ${good ? "good" : v.status === "confirm" ? "needs a person" : "on hold"} ${good === g.closest(".rc").classList.contains("good") ? "✓ as expected" : "✗ not as expected"}`; }
  } catch (e) { $("#result").innerHTML = `<p class="st-head st-refused">Not read: ${esc(e.message)}</p>`; if (stage) stage.fail(); }
  finally { lock(false); setCount(+$("#n").textContent); poll(); }
}

document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => stage && stage.view(b.dataset.view)));
document.querySelectorAll("[data-sample]").forEach(b => b.addEventListener("click", () => {
  const f = new FormData(); f.append("sample", b.dataset.sample); scan(f, `/stage/sample/${b.dataset.sample}`, b.dataset.title, b.dataset.sample);
}));
$("#six").addEventListener("click", async () => {  // the usual pile: six good bills, one after another, each a real scan
  for (const b of document.querySelectorAll(".rc.good")) {
    const f = new FormData(); f.append("sample", b.dataset.sample); await scan(f, `/stage/sample/${b.dataset.sample}`, b.dataset.title, b.dataset.sample);
    await sleep(4500);  // let the stamp and tray animation finish before the next bill
  }
});
$("#photo").addEventListener("change", e => {
  const file = e.target.files[0]; if (!file) return;
  const f = new FormData(); f.append("files", file); scan(f, URL.createObjectURL(file), file.name); e.target.value = "";
});
$("#cam").addEventListener("click", async () => {
  try {
    const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } } });
    const v = $("#video"); v.srcObject = s; await v.play();
    if (stage) stage.liveCam(v);
    $("#snap").hidden = false; $("#cam").hidden = true;
  } catch (e) { $("#result").innerHTML = '<p class="st-head st-refused">Camera not available. Use "Upload a photo" instead.</p>'; }
});
$("#snap").addEventListener("click", () => {
  const v = $("#video"), c = document.createElement("canvas"); c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext("2d").drawImage(v, 0, 0);
  c.toBlob(b => { const f = new FormData(); f.append("files", b, "camera.jpg"); scan(f, c.toDataURL("image/jpeg", 0.85), "Camera photo"); }, "image/jpeg", 0.92);
});
$("#run").addEventListener("click", async () => {
  $("#run").disabled = true;  // every scan is already matched with the bank; this opens the pay step for what matched
  const res = await fetch("/stage/run", { method: "POST" }), v = await res.json().catch(() => ({}));
  if (res.ok) { window.open(v.url, "_blank"); $("#run").disabled = false; return; }
  $("#result").innerHTML = `<p class="st-head st-refused">${esc(v.error || v.detail || "Nothing to pay yet")}</p>`;
  $("#run").disabled = false; poll();
});

// raw audit trail (folded): real chain entries, polled
let seq = Math.max(0, +$(".stage").dataset.seq - 25), polling = false;
export async function poll() {
  if (polling) return; polling = true;
  try {
    const d = await (await fetch(`/stage/log?after=${seq}`)).json();
    const vm = d.server.vm || {};
    $("#srv").innerHTML = (vm.hostname ? `<span class="pill-vm" title="Read from Vultr's instance metadata service, which only answers inside a Vultr machine">● Vultr instance <b>${esc(vm.hostname)}</b> · ${esc(vm.region)}</span> <span class="pill-id">id ${esc(vm.instance.slice(0, 8))}… (Vultr metadata)</span>`
      : `● ${esc(d.server.host)}`) + ` <span class="pill-id">AI ${esc(d.server.ai)} · books: ${esc(d.server.books)}</span>`;
    const ol = $("#log");
    for (const l of d.lines) { const li = document.createElement("li"); li.className = `k-${l.kind}`;
      li.innerHTML = `<span class="t">${esc(l.at)}</span> <span class="s">#${l.seq}</span> ${esc(l.text)} <span class="h">${esc(l.hash)}</span>`; ol.appendChild(li); }
    while (ol.children.length > 200) ol.firstChild.remove();
    seq = d.seq;
  } catch (e) { $("#srv").textContent = "○ server not reachable"; }
  polling = false;
}
poll(); setInterval(poll, 3000);
