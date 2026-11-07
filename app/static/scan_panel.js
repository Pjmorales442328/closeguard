// app/static/scan_panel.js — the calm "reading your bill" panel: the real server steps appear one at a time at a steady pace,
// a slow progress bar fills, then "Read and checked" rests for a moment before the result fades in. Nothing jumps.
window.ScanPanel = (() => {
  const STEPS = ["Photo received on the Vultr server", "Reader 1 (AI on Vultr) reads it", "Reader 2 (a different AI) reads it",
    "Comparing the two readings", "Checking the numbers with fixed rules"];
  const STEP_MS = 1100, REST_MS = 1600;  // fixed pacing; the server is often faster than a person can follow
  let p = null;

  function build(host, preview) {
    host.innerHTML = `<div class="a-doc a-scan">${preview ? `<img src="${preview}" alt="The photo being read">` : '<div class="a-scan-ph"></div>'}<i class="a-sweep"></i></div>
      <div class="a-info" aria-busy="true"><div class="a-banner calm"><b id="sp-h">Reading your bill</b>
      <p id="sp-p">Two separate AI readers on Vultr read it, then fixed rules check the numbers. This takes a few seconds.</p></div>
      <ol class="a-stages" aria-live="polite">${STEPS.map(t => `<li class="wait"><span></span>${t}</li>`).join("")}</ol>
      <div class="a-prog" aria-hidden="true"><i id="sp-bar"></i></div></div>`;
  }
  function paint() {
    const lis = p.host.querySelectorAll(".a-stages li");
    lis.forEach((li, i) => { const st = i < p.shown ? "done" : i === p.shown && !p.restAt ? "busy" : "wait";
      if (li.className !== st) { li.className = st; li.firstElementChild.textContent = st === "done" ? "✓" : ""; } });
    p.host.querySelector("#sp-bar").style.width = `${Math.max(6, (p.shown / STEPS.length) * 100)}%`;
  }
  function step() {
    if (!p) return;
    const now = Date.now();
    if (p.shown < p.server && now - p.t >= STEP_MS) { p.shown++; p.t = now; paint(); }
    if (p.finished && p.shown >= STEPS.length && !p.restAt) {
      p.restAt = now; paint();
      p.host.querySelector(".a-info").setAttribute("aria-busy", "false");
      p.host.querySelector(".a-banner").classList.add("rest");
      p.host.querySelector("#sp-h").textContent = "Read and checked";
      p.host.querySelector("#sp-p").textContent = "Here is what Closeguard found.";
    }
    if (p.restAt && now - p.restAt >= REST_MS) { clearInterval(p.timer); const done = p.onEnd; p = null; done && done(); }
  }
  return {
    active: () => !!p,
    cancel() { if (p) { clearInterval(p.timer); p = null; } },
    // stages: the server's [[text, state]] while it works, or null once it has finished; returns true while the panel is showing
    feed(host, stages, preview, onEnd) {
      if (!p && !stages) return false;
      if (!p) { build(host, preview); p = { host, shown: 0, server: 0, t: Date.now(), finished: false, restAt: 0, onEnd, timer: setInterval(step, 150) }; paint(); }
      if (stages) p.server = Math.max(p.server, stages.filter(s => s[1] === "done").length);
      else { p.finished = true; p.server = STEPS.length; }
      return true;
    },
  };
})();
