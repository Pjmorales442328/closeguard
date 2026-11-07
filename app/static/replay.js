// app/static/replay.js — "Watch it work": replays this run's RECORDED audit-chain events in the room at display speed (labelled).
(() => {
  const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const PACE = { approval: 1300, run_created: 1500, post: 1500, verify_db: 1400 };
  // display pacing (dashboard-plan 4.5): matcher allows 120 ms per line, refusals 350 ms, model rows 900 ms
  const pace = (e) => e.kind !== "gate_decision" ? (PACE[e.kind] || 600)
    : e.text.startsWith("Model") ? 900 : e.tone === "refuse" ? 350 : 120 * Math.max(1, e.txns.length);
  let ev = [], i = 0, timer = null, playing = false, toks = {}, zones = {}, fill = {}, n = {};

  const slot = (z, k) => { const [x0, y0, c, dx, dy] = zones[z]; return [x0 + (k % c) * dx, y0 + Math.floor(k / c) * dy]; };
  function put(id, z, delay = 0) {
    const t = toks[id];
    if (!t) return;
    const [x, y] = slot(z, fill[z]++);
    t.dataset.zone = z; t.style.transitionDelay = `${delay}ms`; t.style.transform = `translate(${x}px,${y}px)`;
  }
  const inZone = (z) => Object.keys(toks).filter((id) => toks[id].dataset.zone === z);
  const count = (k, d = 1) => { n[k] = (n[k] || 0) + d; $$(`[data-count="${k}"]`).forEach((el) => (el.textContent = n[k])); };
  const pulse = (el, cls, ms = 450) => { el?.classList.add(cls); setTimeout(() => el?.classList.remove(cls), ms); };
  const chip = (id, cls, text) => { const c = $(`#chip-${id}`); if (c) { c.className = `chip ${cls}`; c.textContent = text; } };
  const status = (s) => { const el = $("#rp-status"); if (el) el.textContent = s; };

  function feedLine(e) {  // same fields the server renders; textContent only (no HTML from data)
    const li = document.createElement("li"), div = document.createElement("div"), p = document.createElement("p");
    li.className = `ev-${e.tone}${e.story ? " story" : ""} fresh`; li.dataset.txns = e.txns.join(" ");
    const tm = document.createElement("time"); tm.textContent = e.at.slice(11, 19);
    if (e.who === "model") { const m = document.createElement("span"); m.className = "pill"; m.textContent = "AI"; p.append(m, " "); }
    if (e.how) { const h = document.createElement("span"); h.className = "pill " + e.how; h.textContent = e.how_label; p.append(h, " "); }
    p.append(e.text + " ");
    if (e.rule) { const b = document.createElement("small"); b.className = "muted rid"; b.textContent = e.rule; p.append(b); }
    div.append(p);
    if (e.sub) { const s = document.createElement("small"); s.className = "muted"; s.textContent = e.sub; div.append(s); }
    const a = document.createElement("a"); a.className = "seq"; a.href = `/ledger#e${e.seq}`; a.textContent = `#${e.seq}`;
    li.append(tm, div, a); $("#feed")?.prepend(li);
  }

  function reset() {
    // batch rows are expanded to their members and everything is put back in chain (seq) order;
    // the batch's own feed line is written once, when its first member plays
    ev = JSON.parse($("#events-json")?.textContent || "[]")
      .flatMap((r) => r.batch ? r.items.map((it, j) => ({ ...it, _batch: j === 0 ? r : null, _quiet: j > 0 })) : [r])
      .sort((a, b) => a.seq - b.seq);
    zones = JSON.parse($(".room-svg")?.dataset.zones || "{}");
    toks = Object.fromEntries($$(".tok").map((t) => [t.dataset.id, t]));
    fill = Object.fromEntries(Object.keys(zones).map((z) => [z, 0])); n = {};
    $$("[data-count]").forEach((el) => (el.textContent = "0"));
    Object.keys(toks).forEach((id) => put(id, "bank"));
    $("#feed").replaceChildren();
    $("#vault-ok")?.classList.remove("on"); $("#noentry")?.classList.remove("hit"); $("#vault-alarm")?.classList.remove("on");
    chip("agent", "work", "Agent: proposing"); chip("guard", "", "Guard: rules loaded"); chip("maria", "warn", "Maria: waiting");
    chip("journal", "", "Journal: empty"); $("#ana")?.classList.remove("relieved");
    $("#replay-label").hidden = false; $("#room")?.classList.add("replaying"); i = 0;
  }

  function apply(e) {
    const robot = $("#robot"), bar = $("#barrier"), light = $("#guard-light");
    if (e.kind === "run_created") {
      robot?.classList.add("working");
      Object.keys(toks).forEach((id, k) => put(id, "desk", k * 8));
    } else if (e.kind === "gate_decision") {
      const ok = e.tone !== "refuse", k = e.txns.length, g = $("#guard");
      e.txns.forEach((id, j) => { put(id, ok ? "waiting" : "held", j * 14); pulse(toks[id], "ping"); });
      bar?.classList.toggle("allow", ok); light?.classList.remove("allow", "refuse"); light?.classList.add(ok ? "allow" : "refuse");
      g?.classList.remove("allow", "refuse"); g?.classList.add(ok ? "allow" : "refuse");
      if (!e.text.includes("found no invoice") && !e.text.includes("no invoice for")) count("proposed", k);
      count(ok ? "allowed" : "refused", k); count(ok ? "z-waiting" : "z-held", k);
      if (e.tone === "flag") count("flagged", k);
      chip("guard", ok ? (e.tone === "flag" ? "warn" : "ok") : "bad",
        ok ? `Guard: ${e.tone === "flag" ? "flagged" : "allowed"} ${e.txns[0]}${k > 1 ? ` +${k - 1}` : ""}` : `Guard: held ${e.txns[0]}, ${e.rule_label || "a check failed"}`);
    } else if (e.kind === "approval" && e.tone === "approve") {
      robot?.classList.remove("working"); bar?.classList.remove("allow");
      e.txns.forEach((id, k) => put(id, "approved", k * 14));
      $("#maria")?.classList.add("stamping"); setTimeout(() => $("#maria")?.classList.remove("stamping"), 900);
      count("approved", e.txns.length); count("z-approved", e.txns.length); count("z-waiting", -e.txns.length);
      chip("maria", "ok", `Maria: stamped ${n.approved}`); chip("agent", "", "Agent: idle");
    } else if (e.kind === "approval" && e.actor === "agent") {
      $("#noentry")?.classList.add("hit"); window.closeRoom?.walkToDoor(); chip("agent", "bad", "Agent: turned away");
    } else if (e.kind === "post") {
      const ids = inZone("approved");
      ids.forEach((id, k) => put(id, "vault", k * 14));
      count("posted", ids.length); count("z-vault", ids.length); count("z-approved", -ids.length);
      chip("journal", "post", `Journal: ${e.text.replace("Posted ", "")}`);
    } else if (e.kind === "verify_db") {
      const good = e.tone === "post";
      $("#vault-ok")?.classList.toggle("on", good); $("#ana")?.classList.toggle("relieved", good);  // Ana relaxes only on a real match
      chip("journal", good ? "post" : "bad", good ? "Journal: verified by the reader" : "Journal: VERIFY FAILED");
    }
    const scr = $("#agent-screen"); if (scr && e.short) scr.textContent = `> ${e.short}`;
    if (!e._quiet) feedLine(e._batch || e);
    status(`Event ${i + 1} of ${ev.length}: replaying recorded events at display speed (${$("#rp-speed")?.value || 1}×).`);
  }

  function tick() {
    if (i >= ev.length) return stop(true);
    apply(ev[i++]);
    if (playing) timer = setTimeout(tick, pace(ev[i - 1]) / +($("#rp-speed")?.value || 1));
  }
  function play() {
    if (!ev.length || i >= ev.length || !i) reset();
    playing = true; $("#rp-play").textContent = "Pause"; $("#rp-play").setAttribute("aria-pressed", "true");
    tick();
  }
  function stop(done) {
    clearTimeout(timer); playing = false;
    const b = $("#rp-play"); if (b) { b.textContent = done ? "Replay" : "Resume"; b.setAttribute("aria-pressed", "false"); }
    $("#robot")?.classList.remove("working");
    if (done) { $("#room")?.classList.remove("replaying"); status(`Replay finished: ${ev.length} recorded events. This is the current state of the run.`); i = 0; }
  }
  window.closeReplay = { stop: () => stop(false) };

  document.addEventListener("click", (e) => {
    const id = e.target.closest?.("button")?.id;
    if (id === "rp-play" || id === "watch-btn") {
      if (id === "watch-btn") { $("#room")?.scrollIntoView({ behavior: "smooth", block: "nearest" }); i = 0; return play(); }
      playing ? stop(false) : play();
    } else if (id === "rp-step") {
      if (playing) stop(false);
      if (!i) reset();
      tick();
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    if ($("#run-body[data-autoplay]")) setTimeout(play, 700);
  });
})();
