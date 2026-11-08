// app/static/assist.js — the Closeguard assistant panel (speaks what it found, offers to draft supplier emails, hears yes/no) and the app's toasts.
import { holdToTalk, speak } from "/static/mic.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
let offer = null, shownKeys = "", busy = false;

// toasts: short confirmations that auto-dismiss; an optional button jumps to a tab
window.appToast = (text, { kind = "ok", tab = null, label = "" } = {}) => {
  const t = document.createElement("div");
  t.className = `a-toast ${kind}`;
  t.innerHTML = `<span>${esc(text)}</span>${tab ? `<button>${esc(label)}</button>` : ""}`;
  if (tab) t.querySelector("button").onclick = () => { window.appShow(tab); t.remove(); };
  $("#toasts").append(t);
  while ($("#toasts").children.length > 3) $("#toasts").firstElementChild.remove();  // never more than three on screen
  setTimeout(() => t.classList.add("out"), 5500); setTimeout(() => t.remove(), 6000);
};

const state = on => $("#agent").classList.toggle("talking", on);
function waiting(o) {  // a voicemail: nothing pops up or talks until Ana clicks it
  offer = o; shownKeys = o.keys.join(","); $("#ag-vm").hidden = false;
}
$("#ag-vm").onclick = () => { $("#ag-vm").hidden = true; if (offer) open(offer); };
function open(o) {
  $("#ag-say").innerHTML = esc(o.text) + (o.items.length ? `<ul class="a-ag-list">${o.items.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""); $("#ag-heard").hidden = true; $("#ag-hint").textContent = "Click, or hold the mic and say yes or no.";
  $("#ag-act").hidden = false; $("#agent").hidden = false; $("#agent").classList.remove("done");
  speak(o.say, state);
}
function close() { $("#agent").hidden = true; $("#ag-vm").hidden = true; offer = null; }

async function answer(text, heard = "") {
  if (!offer || busy) return;
  busy = true; $("#ag-hint").textContent = "…";
  const f = new FormData(); f.append("keys", offer.keys.join(",")); f.append("text", text); f.append("heard", heard);
  try {
    const d = await (await fetch("/mail/offer", { method: "POST", body: f })).json();
    $("#ag-say").textContent = d.reply.text; speak(d.reply, state);
    if (!d.ok) { $("#ag-hint").textContent = "Click a button, or hold the mic and try again."; return; }
    offer = null; $("#ag-act").hidden = true; $("#agent").classList.add("done");
    if (d.drafted.length) {
      $("#ag-hint").innerHTML = '<button class="a-btn go" id="ag-open">Open Emails</button>';
      $("#ag-open").onclick = () => { window.appShow("mail"); close(); };
      window.appToast(`${d.drafted.length} email draft${d.drafted.length > 1 ? "s" : ""} ready for you to check`, { tab: "mail", label: "Open Emails" });
    } else { $("#ag-hint").textContent = ""; setTimeout(close, 4000); }
  } catch (e) { $("#ag-hint").textContent = "Could not reach the server. Try again."; }
  finally { busy = false; }
}

$("#ag-yes").onclick = () => answer("yes");
$("#ag-no").onclick = () => answer("no");
$("#ag-x").onclick = close;
holdToTalk($("#ag-mic"), {
  onHint: t => { $("#ag-hint").textContent = t; },
  onText: t => { $("#ag-heard").hidden = false; $("#ag-heard").textContent = `You said: “${t}”`; answer(t, t); },
});
// mail.js polls /mail/state every second and passes the offer on; wait until scans and the bank tick-off have finished
document.addEventListener("cg:mail", e => {
  const o = e.detail.offer;
  if (o && !(window.appBusy && window.appBusy()) && o.keys.join(",") !== shownKeys) waiting(o);
  if (!o && offer) close();  // answered elsewhere (the scan room)
});
