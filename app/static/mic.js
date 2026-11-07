// app/static/mic.js — push-to-talk: hold the button, release, the clip is transcribed by Vultr Whisper (/stage/hear). Shared by the scan room and the app.
export function holdToTalk(btn, { onText, onHint }) {
  let rec = null;
  async function start() {
    if (rec) return;
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true }), chunks = [];
      const mt = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      rec = new MediaRecorder(s, mt ? { mimeType: mt } : {});
      rec.ondataavailable = e => chunks.push(e.data);
      rec.onstop = async () => {
        s.getTracks().forEach(t => t.stop());
        onHint("Transcribing on Vultr…");
        const f = new FormData(); f.append("audio", new Blob(chunks, { type: rec?.mimeType || "audio/webm" }), "a.webm"); rec = null;
        try {
          const r = await fetch("/stage/hear", { method: "POST", body: f }), d = await r.json();
          if (!r.ok) return onHint(d.error);
          onText(d.heard);
        } catch (e) { onHint("Could not reach the server: type or click instead."); }
      };
      rec.start(); btn.setAttribute("aria-pressed", "true"); onHint("Listening… release to stop.");
      setTimeout(stop, 12000);
    } catch (e) { rec = null; onHint("Microphone not available: type or click instead."); }
  }
  function stop() { btn.setAttribute("aria-pressed", "false"); if (rec && rec.state !== "inactive") rec.stop(); }
  btn.addEventListener("pointerdown", start);
  ["pointerup", "pointerleave"].forEach(e => btn.addEventListener(e, stop));
  btn.addEventListener("keydown", e => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); start(); } });
  btn.addEventListener("keyup", e => { if (e.key === " " || e.key === "Enter") stop(); });
}

// speak a server sentence: Vultr TTS audio, else the browser's own voice reads the same words
let audio = null;
export function speak(say, onState = () => {}) {
  if (!say) return;
  if (audio) audio.pause();
  audio = new Audio(`/voice/audio/${say.key}`);
  onState(true);
  audio.onended = () => onState(false);
  audio.play().catch(() => {
    onState(false);
    if (window.speechSynthesis) speechSynthesis.speak(new SpeechSynthesisUtterance(say.text));
  });
}
