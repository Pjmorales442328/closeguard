// app/static/pin.js — Maria's PIN as a pop-up: any form with a PIN field asks for it in a dialog on submit.
// The PIN is still checked on the server; while this browser is remembered (signed cookie, 1 hour) no dialog is shown.
(() => {
  const b = document.body, until = Number(b.dataset.pinUntil) || 0, demo = b.dataset.demoPin || "";
  document.querySelectorAll("time[data-until]").forEach(t => {
    t.textContent = new Date(Number(t.dataset.until) * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  });
  const forms = [...document.querySelectorAll("form")].filter(f => f.querySelector("input[name=pin]"));
  if (!forms.length || !window.HTMLDialogElement) return;  // no dialog support: the PIN boxes stay as they are

  const d = document.createElement("dialog");
  d.className = "pin-dlg";
  d.setAttribute("aria-labelledby", "pin-t");
  d.innerHTML = `<form method="dialog"><p class="pin-who"><span class="a-av m">M</span> Maria confirms</p><h2 id="pin-t"></h2>
    <label>Maria's PIN<input type="password" inputmode="numeric" autocomplete="off" maxlength="12" required></label>
    <label class="pin-rem"><input type="checkbox" checked> Remember me on this browser for 1 hour</label>
    <p class="pin-hint"></p>
    <div class="pin-act"><button type="button" class="a-btn" data-x>Cancel</button><button class="a-btn go">Confirm</button></div></form>`;
  b.append(d);
  d.querySelector(".pin-hint").textContent = `Checked on the server. Demo PIN: ${demo}`;  // text, never HTML
  const [pin, rem] = d.querySelectorAll("input");
  let target = null, submitter = null;

  forms.forEach(f => {
    const p = f.querySelector("input[name=pin]");
    p.required = false;
    (p.closest("label") || p).style.display = "none";  // inline style: page CSS gives these labels a display that beats [hidden]
    if (!f.querySelector("input[name=remember]")) f.insertAdjacentHTML("beforeend", '<input type="hidden" name="remember">');
    f.addEventListener("submit", e => {
      if (f.dataset.pinOk || until * 1000 > Date.now()) return;  // confirmed in the dialog, or remembered: send as is
      e.preventDefault();
      target = f;
      submitter = e.submitter || null;
      d.querySelector("h2").textContent = (e.submitter || f.querySelector("button")).textContent.trim();
      pin.value = "";
      d.showModal();
      pin.focus();
    });
  });
  d.querySelector("[data-x]").addEventListener("click", () => d.close());
  d.querySelector("form").addEventListener("submit", () => {
    const f = target;
    if (!f) return;
    target = null;
    f.querySelector("input[name=pin]").value = pin.value;
    f.querySelector("input[name=remember]").value = rem.checked ? "yes" : "";
    f.dataset.pinOk = "1";
    setTimeout(() => {
      f.requestSubmit(submitter);
      f.querySelector("input[name=pin]").value = "";  // the form data is already taken: a download page that stays put
      delete f.dataset.pinOk;                         // must ask again next time (unless remembered)
    }, 0);
  });
})();
