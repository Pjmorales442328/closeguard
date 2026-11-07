// app/static/scene.js — console behaviour: ops tabs, room inspector, glide papers to their new zone after a real action, tamper alarm.
(() => {
  const still = window.matchMedia("(prefers-reduced-motion: reduce)");
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  let tab = "t-live", before = null;

  function tabs() {  // WAI-ARIA tabs: click or arrow keys; selection survives htmx swaps
    const list = $(".ops .tabs");
    if (!list) return;
    const btns = $$("[role=tab]", list);
    const show = (id, focus) => {
      tab = id;
      btns.forEach((b) => {
        const on = b.id === id;
        b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1;
        document.getElementById(b.getAttribute("aria-controls")).hidden = !on;
        if (on && focus) b.focus();
      });
    };
    btns.forEach((b, i) => {
      b.onclick = () => show(b.id);
      b.onkeydown = (e) => {
        const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (d) { e.preventDefault(); show(btns[(i + d + btns.length) % btns.length].id, true); }
      };
    });
    show(btns.some((b) => b.id === tab) ? tab : btns[0].id);
  }

  function inspect(e) {  // click a paper (or a feed line) to read why it sits where it sits
    const t = e.target.closest?.(".tok"), box = $("#room-inspector");
    if (t && box) {
      $$(".tok.sel").forEach((x) => x.classList.remove("sel"));
      t.classList.add("sel");
      box.textContent = t.dataset.info;
      return;
    }
    const li = e.target.closest?.(".feed li[data-txns]");
    if (li && li.dataset.txns && !e.target.closest("a")) {
      const ids = li.dataset.txns.split(" ");
      $$(".tok").forEach((x) => x.classList.toggle("sel", ids.includes(x.dataset.id)));
      const first = $(`.tok[data-id="${ids[0]}"]`);
      if (box && first) box.textContent = (ids.length > 1 ? `${ids.length} papers highlighted. First: ` : "") + first.dataset.info;
    }
  }

  function glide() {  // FLIP: papers whose zone changed after approve/post travel from their old spot
    let moved = 0;
    $$(".tok").forEach((t) => {
      const old = before.get(t.dataset.id);
      if (!old || old.zone === t.dataset.zone) return;
      const to = t.style.transform;
      t.style.transition = "none"; t.style.transform = old.tf;
      t.getBoundingClientRect();
      t.style.transition = ""; t.style.transitionDelay = `${Math.min(moved++ * 12, 600)}ms`;
      t.style.transform = to;
      if (t.dataset.zone === "approved") $("#maria")?.classList.add("stamping");
    });
    if (before.sod !== ($("#noentry text")?.textContent || "") && $("#noentry.hit")) walkToDoor();
  }

  function walkToDoor() {  // the agent tries the controller's door and is turned away (driven by a real SoD refusal)
    const r = $("#robot"), n = $("#noentry");
    if (!r) return;
    r.classList.add("walking"); r.style.transform = "translate(668px,252px)";
    setTimeout(() => { n?.classList.add("flash"); r.style.transform = "translate(415px,116px)"; }, 950);
    setTimeout(() => { r.classList.remove("walking"); n?.classList.remove("flash"); }, 2100);
  }
  window.closeRoom = { walkToDoor };

  document.addEventListener("click", inspect);
  document.addEventListener("htmx:beforeSwap", (e) => {
    if (e.detail.target.id !== "run-body") return;
    window.closeReplay?.stop();
    before = new Map($$(".tok").map((t) => [t.dataset.id, { zone: t.dataset.zone, tf: t.style.transform }]));
    before.sod = $("#noentry text")?.textContent || "";
  });
  document.addEventListener("htmx:afterSettle", (e) => {
    if (e.detail.target.id === "tamper-out") {
      const broken = !!$("#tamper-out .flash.bad");
      $("#vault-alarm")?.classList.toggle("on", broken);
      return;
    }
    if (e.detail.target.id !== "run-body") return;
    tabs();
    if (before && !still.matches) glide();
    before = null;
  });
  document.addEventListener("DOMContentLoaded", tabs);
})();
