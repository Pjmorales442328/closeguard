// app/static/stage_talk.js — the server speaks a discrepancy (Vultr TTS), Ana answers by push-to-talk (Vultr Whisper) or typing.
import { esc, poll, showResult } from "/static/stage.js";

const $ = s => document.querySelector(s);
import { holdToTalk, speak as play } from "/static/mic.js";
let bill = null;

function speak(say) {
  if (!say) return;
  $("#say").innerHTML = `🔊 <b>Closeguard:</b> ${esc(say.text)}`;
  if (document.visibilityState !== "visible") return;  // a scan room left open in another tab must not talk over the app
  play(say, on => document.body.classList.toggle("speaking", on));
}

export const talk = {
  start(v) { bill = v.id; $("#maria").hidden = true; $("#ans").value = "";
    if (!v.say) return this.hide(); $("#talk").hidden = false; speak(v.say); },
  hide() { $("#talk").hidden = true; bill = null; },
};

async function send() {
  const text = $("#ans").value.trim(); if (!text || !bill) return;
  const f = new FormData(); f.append("bill", bill); f.append("text", text); f.append("heard", $("#ans").dataset.heard || "");
  const d = await (await fetch("/stage/answer", { method: "POST", body: f })).json();
  $("#talk-hint").innerHTML = d.drafted?.length ? `✓ Email drafted for ${esc(d.drafted.join(", "))}. <a href="/app#mail" target="_blank">Open Emails ↗</a>`
    : d.noted ? `Noted from Ana: ${esc(d.noted)}` : "Not understood; try again.";
  $("#ans").value = ""; delete $("#ans").dataset.heard;
  $("#maria").hidden = !d.ready_for_maria; speak(d.reply); poll();
}

holdToTalk($("#mic"), {
  onHint: t => { $("#talk-hint").textContent = t; },
  onText: t => { $("#ans").value = t; $("#ans").dataset.heard = t; $("#talk-hint").textContent = "Check the words, edit if needed, then press Send."; },
});
$("#send").addEventListener("click", send);
$("#ans").addEventListener("keydown", e => { if (e.key === "Enter") send(); });
$("#maria").addEventListener("click", async () => {
  const f = new FormData(); f.append("bill", bill);
  const d = await (await fetch("/stage/confirm", { method: "POST", body: f })).json();
  if (d.v) showResult(d.v);
  $("#maria").hidden = true; speak(d.reply); poll();
});
