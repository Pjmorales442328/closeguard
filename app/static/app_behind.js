// app/static/app_behind.js — the app's "Behind the scenes" panel: follows the newest scan job step by step, demo bills, Clear demo.
import { applyStep, resetTimeline } from "/static/timeline.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const sleep = ms => new Promise(f => setTimeout(f, ms));
let shown = null, following = false;

async function follow(id) {  // replay the job's real server steps as they arrive
  following = true; resetTimeline("New bill"); let seen = 0;
  try {
    for (let i = 0; i < 400; i++) {
      const j = await (await fetch(`/stage/job/${id}`)).json();
      j.steps.slice(seen).forEach(applyStep); seen = j.steps.length;
      if (j.done) break;
      await sleep(250);
    }
  } catch (e) { /* the next poll tries again */ }
  following = false;
}

async function latest() {
  if (following) return;
  try {
    const { job } = await (await fetch("/stage/latest")).json();
    if (job && job !== shown) { shown = job; follow(job); }
  } catch (e) { /* server restarting: keep the last view */ }
}

async function server() {
  try {
    const d = (await (await fetch("/stage/log?after=999999999")).json()).server, vm = d.vm || {};
    $("#srv").innerHTML = (vm.hostname ? `<span class="pill-vm">● Vultr instance <b>${esc(vm.hostname)}</b> · ${esc(vm.region)}</span> ` : `● ${esc(d.host)} `)
      + `<span class="pill-id">AI ${esc(d.ai)} · books: ${esc(d.books)}</span>`;
  } catch (e) { $("#srv").textContent = "○ server not reachable"; }
}

document.querySelectorAll(".bh-btn[data-sample]").forEach(b => b.addEventListener("click", async () => {
  const f = new FormData(); f.append("sample", b.dataset.sample);
  const r = await fetch("/stage/scan", { method: "POST", body: f });
  if (!r.ok) window.appToast((await r.json().catch(() => ({}))).error || "Could not start that scan.", { kind: "bad" });
  latest();
}));

let armed = false;
$("#bh-clear").addEventListener("click", async () => {  // two clicks, like Remove: Clear wipes everyone's demo month
  const b = $("#bh-clear");
  if (!armed) { armed = true; b.textContent = "Click again to clear"; setTimeout(() => { armed = false; b.textContent = "Clear demo"; }, 4000); return; }
  armed = false; b.textContent = "Clear demo";
  await fetch("/stage/clear", { method: "POST" }).catch(() => {});
  shown = null; $("#tl").innerHTML = '<li class="bh-empty">Cleared. The six normal bills load again in about 10 seconds.</li>';
  window.appToast("Demo cleared. The normal bills load again in about 10 seconds.");
});

server(); setInterval(server, 10000);
latest(); setInterval(latest, 800);
