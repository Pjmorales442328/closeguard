// desk.js — Guard Desk: camera feed, frame grab, photo/sample upload, scan line while the request runs (no other state).
(() => {
  const $ = (id) => document.getElementById(id);
  const msg = (t) => { const m = $("screen-msg"); m.textContent = t; m.hidden = !t; };
  async function post(fd) {
    const w = document.querySelector(".window"); w.classList.add("scanning"); msg("Reading… both readers take a few seconds.");
    try {
      const r = await fetch("/desk/scan", { method: "POST", body: fd, headers: { "X-Desk": "1" } });
      $("desk-result").innerHTML = await r.text();
      const id = $("desk-result").querySelector("[data-bill]");
      document.querySelector("#voice-card input[name=bill]").value = id ? id.dataset.bill : "";
      msg(r.ok ? "" : "The scan was refused. See the reason on the right.");
    } catch (e) { $("desk-result").innerHTML = '<p class="flash bad" role="alert">Network problem: the scan did not reach the server.</p>'; msg("Scan failed."); }
    w.classList.remove("scanning");
  }
  document.addEventListener("htmx:afterSwap", () => { const c = document.querySelector("#voice-card .captions"), b = $("bubble"); b.textContent = c ? c.textContent : ""; b.hidden = !c; });
  function show(src) { $("still").src = src; $("still").hidden = false; $("cam").hidden = true; }
  $("cam-btn").onclick = async () => {
    try {
      $("cam").srcObject = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      await $("cam").play(); $("cam").hidden = false; $("still").hidden = true; $("scan-btn").disabled = false; msg("");
    } catch (e) { msg("Camera not available here. Use the photo button or a sample bill."); }
  };
  $("scan-btn").onclick = () => {
    const v = $("cam"), c = $("grab"), k = Math.min(1, 1600 / Math.max(v.videoWidth, v.videoHeight));
    c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k); c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    c.toBlob((b) => { show(URL.createObjectURL(b)); const fd = new FormData(); fd.append("files", b, "scan.jpg"); post(fd); }, "image/jpeg", 0.85);
  };
  $("file-in").onchange = (e) => { const f = e.target.files[0]; if (!f) return; show(URL.createObjectURL(f)); const fd = new FormData(); fd.append("files", f, f.name); post(fd); };
  document.querySelector(".samples").addEventListener("click", (e) => {
    const b = e.target.closest("[data-sample]"); if (!b) return; e.preventDefault();
    show(b.querySelector("img").src); const fd = new FormData(); fd.append("sample", b.dataset.sample); post(fd);
  });
})();
