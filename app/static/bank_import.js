// app/static/bank_import.js — Bank statement tab: import the bank's CSV export (or the sample); the server matches every scanned bill at once.
const $ = s => document.querySelector(s);

async function send(form) {
  const r = await fetch("/app/bank/import", { method: "POST", body: form }), d = await r.json().catch(() => ({}));
  if (!r.ok) return window.appToast(d.error || "Could not import that file.", { kind: "bad" });
  window.appToast(`Bank statement imported: ${d.source}. Every scanned bill is matched with it now.`);
  window.appShow && window.appShow("bank");
}

$("#bank-file")?.addEventListener("change", e => {
  const file = e.target.files[0]; if (!file) return;
  const f = new FormData(); f.append("file", file); send(f); e.target.value = "";
});
$("#bank-sample")?.addEventListener("click", () => { const f = new FormData(); f.append("sample", "1"); send(f); });
