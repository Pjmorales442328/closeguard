// voice.js — push-to-talk recorder, transcript upload, spoken-answer fallback, approve-form pre-fill (never submits).
(() => {
  let rec = null, timer = null;
  const hint = (t) => { const h = document.getElementById("voice-hint"); if (h) h.textContent = t; };
  const talking = (on) => document.body.classList.toggle("talking", on);
  const swap = (html) => { const c = document.getElementById("voice-card"); c.outerHTML = html; window.htmx && htmx.process(document.getElementById("voice-card")); };
  async function start() {
    if (rec) return;
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mt = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      const chunks = [], r = new MediaRecorder(s, mt ? { mimeType: mt } : {});
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = () => { s.getTracks().forEach((t) => t.stop()); send(new Blob(chunks, { type: r.mimeType || "audio/webm" })); };
      rec = r; r.start(); timer = setTimeout(stop, 15000);
      document.getElementById("mic").setAttribute("aria-pressed", "true"); hint("Listening… release to stop (15 s max).");
    } catch (e) { rec = null; hint("Microphone not available. Type your question instead."); }
  }
  function stop() { clearTimeout(timer); if (rec) { const r = rec; rec = null; r.state !== "inactive" && r.stop(); } const m = document.getElementById("mic"); m && m.setAttribute("aria-pressed", "false"); }
  async function send(blob) {
    hint("Transcribing…");
    const fd = new FormData(); fd.append("audio", blob, "q.webm"); fd.append("bill", document.querySelector("#voice-card input[name=bill]").value);
    try {
      const r = await fetch(`/runs/${document.getElementById("voice-card").dataset.run}/voice/transcribe`, { method: "POST", body: fd, headers: { "HX-Request": "true" } });
      if (!r.ok) return hint(r.status === 413 ? "Recording too long. Type instead." : "Could not read that recording. Type instead.");
      swap(await r.text());
    } catch (e) { hint("Network problem. Type your question instead."); }
  }
  function browserVoice(text, why) {
    if (!window.speechSynthesis || !text) return;
    const u = new SpeechSynthesisUtterance(text); u.onstart = () => talking(true); u.onend = () => talking(false);
    speechSynthesis.cancel(); speechSynthesis.speak(u); hint(why);
  }
  document.addEventListener("pointerdown", (e) => { if (e.target.closest("#mic")) { e.preventDefault(); start(); } });
  document.addEventListener("pointerup", () => rec && stop());
  document.addEventListener("click", (e) => {
    if (e.target.closest("#mic") && e.detail === 0) rec ? stop() : start();  // keyboard: space/enter toggles
    const f = e.target.closest("[data-fill-role]");
    if (!f) return;
    const form = document.getElementById("approver");
    if (f.dataset.fillName) form.elements.approver.value = f.dataset.fillName;
    if (f.dataset.fillRole) form.elements.role.value = f.dataset.fillRole;
    form.elements.approver.focus();
  });
  document.addEventListener("htmx:afterSwap", () => { const b = document.querySelector("#voice-card [data-browser-voice]"); if (b) browserVoice(b.dataset.browserVoice, "Browser voice: this answer has no server audio on this build."); });
  document.addEventListener("click", (e) => { const b = e.target.closest("[data-browser-voice]"); if (b) browserVoice(b.dataset.browserVoice, "Browser voice: this answer has no server audio on this build."); });
  document.addEventListener("error", (e) => { if (e.target.matches && e.target.matches("#voice-card audio")) browserVoice(e.target.dataset.caption, "Server voice failed for this answer: using the browser voice."); }, true);
  document.addEventListener("playing", (e) => { if (e.target.matches && e.target.matches("#voice-card audio")) hint(""); }, true);
  for (const ev of ["play", "pause", "ended"]) document.addEventListener(ev, (e) => { if (e.target.matches && e.target.matches("#voice-card audio")) talking(ev === "play"); }, true);
})();
