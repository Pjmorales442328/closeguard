// app/static/app.js — bookkeeper app: polls /app/state, draws the bill list and the selected bill; add a photo; pay the ready bills.
(() => {
  const $ = s => document.querySelector(s), embed = document.body.classList.contains("embed");
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const date = d => { if (!d) return ""; const x = new Date(d + "T00:00:00"); return x.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); };
  window.appShow = t => show(t);
  let dueBy = {}, justRead = "", sel = null, newest = null, tab = "bills", booted = false, preview = null, uploading = false, calmUntil = 0, fade = false, shownBills = [];
  window.appBusy = () => window.ScanPanel.active() || Date.now() < calmUntil;  // the assistant waits until the result has settled
  const onEnd = () => { calmUntil = Date.now() + 1500; fade = true; preview = null; tick(); };

  function show(t) {
    tab = t; document.querySelectorAll(".a-pane").forEach(p => p.hidden = p.id !== t);
    document.querySelectorAll("[data-tab]").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
    if (!embed) history.replaceState(null, "", "#" + t);
  }
  // bank statement: every scan is matched right away; a row whose status just changed flashes, and a toast says what happened
  let prev = null, bankSig = "";
  function bank(k) {
    const was = prev || {}; prev = Object.fromEntries(k.lines.map(x => [x.txn, x.kind + x.text]));
    const changed = booted ? k.lines.filter(x => x.kind !== "wait" && was[x.txn] !== undefined && was[x.txn] !== x.kind + x.text) : [];
    booted = true;
    const ok = k.lines.filter(x => x.kind === "pay").length, bad = k.lines.filter(x => ["hold", "check"].includes(x.kind)).length, waiting = k.count - ok - bad;
    const sig = JSON.stringify(k.lines);  // redraw only on change, so a flashing row keeps flashing
    if (sig !== bankSig) $("#bank-rows").innerHTML = k.lines.map(x => `<tr class="${x.kind}${changed.includes(x) ? " new" : ""}"><td>${esc(date(x.date))}</td><td>${esc(x.who)}</td>
      <td>${esc(x.ref)}</td><td class="r">$${esc(x.amount)}</td><td>${x.kind === "pay" ? "✓ " : x.kind === "hold" ? "✗ " : x.kind === "check" ? "? " : ""}${esc(x.text)}</td></tr>`).join("");
    bankSig = sig;
    $("#bank-held").innerHTML = k.unpaid_held.length ? `<div class="a-held"><b>On hold and not paid</b>${k.unpaid_held.map(x => `<p><span class="pill ${x.kind}">${x.kind === "hold" ? "On hold" : "Needs checking"}</span>
      <b>${esc(x.who)}</b> bill ${esc(x.ref)}, $${esc(x.total)}</p><p class="why">Not on this statement, so nothing was paid for it. ${x.note ? "Reason: " + esc(x.note) : ""}</p>`).join("")}</div>` : "";
    $("#bank-sum").innerHTML = `${k.count} payments left the bank account in October ($${esc(k.total)}). Each bill you scan is matched with them right away. `
      + `<b class="ok">${ok} match a checked bill</b>` + (bad ? `, <b class="bad">${bad} need a look</b>` : "") + (waiting ? `, ${waiting} still waiting for their bill.` : ".");
    $("#s-bank").textContent = `${ok} of ${k.count} matched`;
    $("#s-bank2").textContent = bad ? `${bad} need a look` : waiting ? `${waiting} waiting for their bill` : "all matched";
    if (!embed && window.appToast) changed.forEach(x => x.kind === "pay"
      ? window.appToast(`Matched with the bank: ${x.who} $${x.amount} on ${date(x.date)}.`, { tab: "bank", label: "See it" })
      : x.kind !== "wait" && x.who !== justRead && window.appToast(`Bank: ${x.who} $${x.amount}. ${x.text}.`, { kind: "bad", tab: "bank", label: "See it" }));
    if (embed && changed.length) setTimeout(() => show("bank"), 2500);  // the 3D PC: after the bill lands, show its bank row turning green or red
    const url = k.run && ok ? `/simple/pay/${k.run}` : "", p = $("#tab-pay");  // step 4 opens once something matched
    p.href = url || "#"; p.toggleAttribute("aria-disabled", !url);
    if (!embed) { $("#pay").disabled = !url; }
  }

  function row(b) {
    return `<li class="a-row ${b.id === sel ? "sel" : ""}" data-id="${esc(b.id)}"><img src="${esc(b.image)}" alt="">
      <span><b>${esc(b.supplier)}</b><small>${b.kind === "check" ? "check the paper before it goes in" : esc(b.invoice_no) + (dueBy[b.id] ? ` · <span class="due ${dueBy[b.id].state}">${esc(dueBy[b.id].text)}</span>` : "")}</small></span>
      <span class="a-amt">${b.total ? "$" + esc(b.total) : ""}${dueBy[b.id]?.state === "paid" ? '<em class="pill paid">Paid</em>' : dueBy[b.id]?.state === "problem" ? '<em class="pill hold">Check the bank</em>' : `<em class="pill ${b.kind}">${esc(b.label)}</em>`}</span></li>`;
  }
  const calmRow = '<li class="a-row scanning"><span class="a-spin"></span><span><b>New bill</b><small>Reading it now…</small></span></li>';
  function banner(b) {  // a checked bill whose payment is already on the bank statement says so, instead of "ready to pay"
    const st = dueBy[b.id]?.state;
    if (b.kind === "pay" && st === "paid") return `<div class="a-banner pay"><b>${esc(dueBy[b.id].text)}</b><p>Its payment is on the October bank statement and matches this bill.</p></div>`;
    if (b.kind === "pay" && st === "problem") return `<div class="a-banner hold"><b>Paid, but the bank shows a problem</b><p>The bill passed every check, but its payment does not match. <a href="#bank" onclick="appShow('bank');return false">See the bank statement</a>.</p></div>`;
    return `<div class="a-banner ${b.kind}"><b>${esc(b.label)}</b>${b.note ? `<p>${esc(b.note)}</p>` : ""}</div>`;
  }
  function detail(b) {
    if (!b) return '<p class="a-empty">Select a bill to see it.</p>';
    const f = b.rows.map(([k, v, d]) => [k, k === "Total" ? "$" + v.replaceAll(" or ", " or $") : v, d]);
    if (b.lines.length && b.kind !== "check") f.splice(4, 0, ["Lines", b.lines.map(x => "$" + x).join(" + "), false]);
    return `<div class="a-doc"><img src="${esc(b.image)}" alt="Photo of the bill"></div>
      <div class="a-info">${banner(b)}

      <dl>${f.map(([k, v, d]) => `<dt>${k}</dt><dd class="${d ? "disp" : ""}">${esc(v) || "–"}${d ? " <small>check the paper</small>" : ""}</dd>`).join("")}</dl>
      <p class="a-read">${b.readers.every(Boolean) ? "✓ Read by two separate AI readers" : "⚠ Only one reader could read it"}, then checked by fixed rules.</p></div>`;
  }
  async function tick() {
    try {
      const d = await (await fetch("/app/state")).json();
      justRead = ""; const stages = d.scanning ? d.scanning.stages : uploading ? [] : null;
      if (window.ScanPanel.feed($("#detail"), stages, preview, onEnd)) {  // calm panel: hold the rest of the page still until it is done
        if (embed) show("bills");
        $("#list").innerHTML = calmRow + shownBills.map(row).join(""); return;
      }
      if (d.bills.length && d.bills[0].id !== newest) {
        const fresh = booted;  // a bill that arrived while this page was open
        newest = d.bills[0].id; if (embed || !sel || fresh) sel = newest; if (embed) show("bills");
        const b = d.bills[0]; justRead = b.supplier;
        if (fresh && !embed && window.appToast) window.appToast(`Bill read: ${b.supplier}, ${b.label.toLowerCase()}.` + (b.kind === "hold" && b.note ? " " + b.note : ""), { kind: b.kind === "pay" ? "ok" : b.kind === "hold" ? "bad" : "warn" });
      }
      shownBills = d.bills; dueBy = d.due.bills; window.AppMoney.render(d);
      $("#list").innerHTML = d.bills.map(row).join("") || '<li class="a-empty">No bills yet. Add a bill photo to start.</li>';
      $("#detail").innerHTML = detail(d.bills.find(b => b.id === sel));
      if (fade) { fade = false; $("#detail").classList.remove("a-fade"); void $("#detail").offsetWidth; $("#detail").classList.add("a-fade"); }
      $("#s-pay").textContent = `${d.summary.pay[0]} bill${d.summary.pay[0] === 1 ? "" : "s"}`; $("#s-amt").textContent = "$" + d.summary.pay[1] + (d.summary.pay[2] ? ` · ${d.summary.pay[2]} already paid` : "");
      $("#s-check").textContent = d.summary.check; $("#s-hold").textContent = d.summary.hold;
      bank(d.bank);
    } catch (e) { /* server busy: next tick */ }
  }
  document.querySelectorAll("[data-tab]").forEach(b => b.addEventListener("click", e => { e.preventDefault(); show(b.dataset.tab); }));
  $("#tab-pay").addEventListener("click", e => { if (e.currentTarget.hasAttribute("aria-disabled")) e.preventDefault(); });
  if (["bills", "bank", "mail", "activity"].includes(location.hash.slice(1))) { show(location.hash.slice(1)); setTimeout(() => scrollTo(0, 0)); }
  $("#list").addEventListener("click", e => { const r = e.target.closest(".a-row[data-id]"); if (r) { sel = r.dataset.id; tick(); } });
  if (!embed) {
    $("#add").addEventListener("change", async e => {
      const file = e.target.files[0]; if (!file) return;
      const f = new FormData(); f.append("files", file); preview = URL.createObjectURL(file); show("bills");
      uploading = true; window.ScanPanel.feed($("#detail"), [], preview, onEnd);
      const r = await fetch("/stage/scan", { method: "POST", body: f }).finally(() => { uploading = false; }); e.target.value = "";
      if (!r.ok) { window.ScanPanel.cancel(); preview = null; window.appToast((await r.json().catch(() => ({}))).detail || "Could not send that photo. Use a PNG or JPEG under 4 MB.", { kind: "bad" }); tick(); }
    });
    $("#pay").addEventListener("click", () => { location.href = $("#tab-pay").href; });
  }
  tick(); setInterval(tick, 700);
})();
