// app/static/mail.js — Emails tab: drafts Ana approves, the conversation, follow-up countdown, a supplier's demo reply and how it was read.
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const STATUS = { draft: "Draft: approve to send", waiting: "Sent, waiting", promised: "Supplier promised", replied: "Replied: needs Ana",
    done: "Solved", flagged: "⚠ Possible scam", no_reply: "No reply: call them" };
  const INTENT = { corrected_bill: "Sending a corrected bill", promise: "Promise", question: "Question for Ana", other: "Other",
    bank_change: "Asks to pay a different bank account" };
  const PRESETS = [["Corrected bill", "Sorry about that. The corrected bill is attached."],
    ["Refund promise", "Apologies for the mix-up. We will refund the second payment by November 20."],
    ["Bank change (scam)", "Please note our bank details have changed. From now on pay to account 4471 2209 at First Island Bank."],
    ["Question", "Can you send us the payment proof first?"]];
  let sel = null, sig = "", data = [];
  const when = t => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  function msg(m, t) {
    const who = m.dir === "in" ? `From ${esc(t.to)}` : `To ${esc(t.to)}${m.auto ? " · automatic follow-up (approved by Ana with the first email)" : m.by ? ` · approved and sent by ${esc(m.by)}` : ""}`;
    const r = m.read, rc = m.meta?.vultr?.id;
    const read = r ? `<div class="a-ai ${r.scam ? "scam" : ""}">${r.scam ? "⚠ Possible scam: they ask to pay a different bank account. " + ({ locked: "Nothing was changed. Payments to them are locked until Maria calls them back on the number you already have.", called_back: "Maria called them back on the number on file: bank details unchanged, lock lifted." }[t.lock] || "Nothing was changed. Call them on the number you already have.") + ""
      : `Closeguard read it: <b>${esc(INTENT[r.intent] || r.intent)}</b> · ${esc(r.summary)}`}<br><small>${esc(m.meta?.how || "")}${rc ? ` · Vultr receipt <code>${esc(rc)}</code>` : ""}</small></div>` : "";
    return `<article class="a-msg ${m.dir}"><header>${who} · ${when(m.at)}</header><pre>${esc(m.body)}</pre>${read}</article>`;
  }
  function detail(t) {
    if (!t) return '<p class="a-empty">Select an email.</p>';
    const head = `<h2>${esc(t.subject)}</h2><p class="a-wait">To ${esc(t.supplier)} &lt;${esc(t.to)}&gt; · ${esc(STATUS[t.status])}</p>`;
    if (t.status === "draft") return head + `<div class="a-msg"><header>Draft written by Closeguard from the check results. Edit anything, then approve.</header>
      <textarea id="draft">${esc(t.msgs[0].body)}</textarea></div><button class="a-btn go" id="approve">Approve &amp; send as Ana</button>`;
    const box = ["waiting", "no_reply"].includes(t.status) || t.status === "promised"
      ? `<div class="a-reply"><h3>Supplier's reply (demo: type it as the supplier)</h3><div class="presets">${PRESETS.map(([k, v]) => `<button data-p="${esc(v)}">${esc(k)}</button>`).join("")}</div>
        <textarea id="rtext" placeholder="The supplier writes back…"></textarea><button class="a-btn" id="rsend">Receive this reply</button></div>` : "";
    return head + `<p class="a-wait" id="cd"></p>` + t.msgs.map(m => msg(m, t)).join("") + box;
  }
  function countdown() {
    const t = data.find(x => x.id === sel), el = $("#cd"); if (!el || !t) return;
    el.textContent = t.status === "waiting" && t.next_at ? `Next automatic follow-up in ${Math.max(0, Math.round(t.next_at - Date.now() / 1000))} s (demo pace; real use: 3 days). ${t.followups} sent so far.` : "";
  }
  async function tick() {
    try {
      const all = await (await fetch("/mail/state")).json();
      data = all.threads; document.dispatchEvent(new CustomEvent("cg:mail", { detail: all }));
      if (!sel && data.length) sel = data[0].id;
      const open = data.filter(t => ["draft", "flagged", "replied", "no_reply"].includes(t.status)).length;
      $("#mail-n").hidden = !open; $("#mail-n").textContent = open;
      $("#threads").innerHTML = data.map(t => `<li class="a-th ${t.id === sel ? "sel" : ""}" data-id="${t.id}"><b>${esc(t.supplier)}</b><small>${esc(t.subject)}</small>
        <em class="pill ${t.status}">${esc(STATUS[t.status])}</em></li>`).join("") || '<li class="a-empty">No emails yet.</li>';
      const t = data.find(x => x.id === sel), s = t ? `${t.id}|${t.status}|${t.msgs.length}` : "";
      if (s !== sig && !(document.activeElement && ["draft", "rtext"].includes(document.activeElement.id))) { sig = s; $("#thread").innerHTML = detail(t); }
      countdown();
    } catch (e) { /* server busy: next tick */ }
  }
  function done(t) {  // confirm what just happened, in words
    if (!window.appToast || !t) return;
    const last = t.msgs[t.msgs.length - 1];
    if (t.status === "waiting") window.appToast(`Sent to ${t.supplier}. If they do not reply, Closeguard follows up in ${t.followup_s} s (demo pace).`);
    else if (t.status === "flagged") window.appToast(`Possible scam in ${t.supplier}'s reply: nothing was changed or paid.`, { kind: "bad" });
    else if (last.read) window.appToast(`Reply read: ${INTENT[last.read.intent] || last.read.intent}.`);
  }
  $("#threads").addEventListener("click", e => { const li = e.target.closest(".a-th"); if (li) { sel = li.dataset.id; sig = ""; tick(); } });
  $("#thread").addEventListener("click", async e => {
    if (e.target.dataset.p) { $("#rtext").value = e.target.dataset.p; return; }
    const post = async (url, k, v) => { const f = new FormData(); f.append(k, v); e.target.disabled = true; e.target.textContent = "…";
      const r = await fetch(url, { method: "POST", body: f }), j = r.ok ? await r.clone().json() : null; sig = ""; await tick(); if (r.ok) done(j); if (!r.ok) $("#thread").insertAdjacentHTML("afterbegin", `<p class="a-warn">${esc((await r.json().catch(() => ({}))).detail || "That did not work.")}</p>`); };
    if (e.target.id === "approve") await post(`/mail/${sel}/send`, "body", $("#draft").value);
    if (e.target.id === "rsend" && $("#rtext").value.trim()) await post(`/mail/${sel}/reply`, "text", $("#rtext").value);
  });
  tick(); setInterval(tick, 1000);
})();
