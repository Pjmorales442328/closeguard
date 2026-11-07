// app/static/app_money.js — the owner's view in the bookkeeper app: money Closeguard stopped, what is due or late, and who did what.
window.AppMoney = (() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const ROLE = { ana: "Ana", maria: "Maria", ai: "AI", rules: "Rules", supplier: "Supplier", books: "Books" };
  let sigS = "", sigA = "";

  function stopped(s) {
    const sig = JSON.stringify(s); if (sig === sigS) return; sigS = sig;
    $("#stop").hidden = !s.count;
    if (!s.count) return;
    $("#stop").innerHTML = `<div class="a-stop-big"><svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><path fill="currentColor" d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5l-8-3Zm-1.2 14.2-3.5-3.5 1.4-1.4 2.1 2.1 4.9-4.9 1.4 1.4-6.3 6.3Z"/></svg>
      <div><b>$${esc(s.total)}</b><span>stopped by Closeguard this month: wrong or unapproved, so not paid or recorded until a person looks</span></div></div>
      <ul>${s.items.map(x => `<li><b>${esc(x.who)}</b> ${esc(x.what)} <em>$${esc(x.amount)}</em></li>`).join("")}</ul>`;
  }
  function due(d) {
    $("#s-due").textContent = d.late[0] ? `${d.late[0]} late` : d.week[0] ? `${d.week[0]} due soon` : "none late";
    $("#s-due2").textContent = d.late[0] ? `$${d.late[1]} past its due date` + (d.week[0] ? `, ${d.week[0]} more due this week` : "")
      : d.week[0] ? `$${d.week[1]} due in the next 7 days` : "nothing due in the next 7 days";
    $("#sum .due").classList.toggle("bad", !!d.late[0]);
  }
  function activity(list) {
    const sig = JSON.stringify(list); if (sig === sigA) return; sigA = sig;
    const t = iso => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    $("#act").innerHTML = list.map(x => `<li class="${x.kind}"><time>${t(x.at)}</time><span class="who">${esc(ROLE[x.kind] || x.who)}<small>${esc(x.role)}</small></span><p>${esc(x.text)}</p></li>`).join("")
      || '<li class="a-empty">Nothing yet. Add a bill photo and every step will be listed here.</li>';
  }
  return { render(d) { stopped(d.stopped); due(d.due); activity(d.activity); } };
})();
