"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

let meta = null;
let state = null;
let step = 0;
let saveTimer = null;

// ------------------------------------------------------------- yardımcılar
function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}

function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  const target = keys.reduce((o, k) => (o[k] ??= {}), obj);
  target[last] = value;
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  return res.json();
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    await api("/api/case", state);
    const s = $("#saved");
    s.classList.add("show");
    setTimeout(() => s.classList.remove("show"), 1200);
  }, 500);
}

function alertBox(kind, title, items) {
  return el("div", { class: `alert ${kind}` }, el("b", {}, title),
    items.length ? el("ul", {}, items.map((i) => el("li", {}, i))) : "");
}

// ------------------------------------------------------------- yükleme
async function loadYear(year) {
  state = await api(`/api/case/${year}`);
  state.tax_year = Number(year);
  bindFields();
  renderEligibility();
  renderTxns();
  updateNav();
}

function bindFields() {
  for (const input of $$("[data-path]")) {
    const v = getPath(state, input.dataset.path);
    if (input.type === "checkbox") input.checked = !!v;
    else input.value = v ?? "";
  }
}

document.addEventListener("input", (e) => {
  const t = e.target;
  if (!t.dataset || !t.dataset.path) return;
  setPath(state, t.dataset.path, t.type === "checkbox" ? t.checked : t.value);
  scheduleSave();
});
document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset && t.dataset.path) {
    setPath(state, t.dataset.path, t.type === "checkbox" ? t.checked : t.value);
    scheduleSave();
  }
});

// ------------------------------------------------------------- uygunluk
function eligible() {
  return meta.eligibility.every(([k]) => state.eligibility[k]);
}

function renderEligibility() {
  const box = $("#eligibility");
  box.replaceChildren();
  for (const [key, text] of meta.eligibility) {
    const cb = el("input", { type: "checkbox" });
    cb.checked = !!state.eligibility[key];
    const label = el("label", { class: cb.checked ? "yes" : "" }, cb, el("span", {}, text));
    cb.addEventListener("change", () => {
      state.eligibility[key] = cb.checked;
      label.className = cb.checked ? "yes" : "";
      scheduleSave();
      updateNav();
    });
    box.append(label);
  }
}

// ------------------------------------------------------------- işlemler
function newTxn() {
  return { date: `${state.tax_year}-01-01`, description: "", category: "", amount_usd: "",
           counterparty: "", paid_by: "llc", notes: "", source: "manual" };
}

function txnNeedsReview(t) {
  return !t.category || !t.amount_usd || t.needs_review;
}

function renderTxns() {
  const tbody = $("#txn-table tbody");
  tbody.replaceChildren();
  const onlyReview = $("#only-review").checked;
  const txns = state.transactions;
  txns.forEach((t, i) => {
    if (onlyReview && !txnNeedsReview(t)) return;
    const change = (field) => (e) => {
      t[field] = e.target.value;
      if (field === "category") t.needs_review = false;
      if (field === "category" || field === "paid_by") renderTxns();
      else { tr.classList.toggle("flag", txnNeedsReview(t)); updateTxnSummary(); }
      scheduleSave();
    };
    const cat = el("select", { onchange: change("category") },
      el("option", { value: "" }, "— Kategori seçin —"),
      Object.entries(meta.categories).map(([k, v]) => el("option", { value: k }, v)));
    cat.value = t.category || "";
    const payer = el("select", { onchange: change("paid_by") },
      el("option", { value: "llc" }, "LLC hesabı"), el("option", { value: "owner" }, "Ortak (kişisel)"));
    payer.value = t.paid_by || "llc";
    const dir = t.direction ? el("div", { class: "dir" }, t.direction === "in" ? "giriş (Mercury)" : "çıkış (Mercury)") : "";
    const tr = el("tr", { class: txnNeedsReview(t) ? "flag" : "" },
      el("td", {}, el("input", { type: "date", value: t.date, oninput: change("date") })),
      el("td", {}, el("input", { value: t.description, placeholder: "Açıklama", oninput: change("description") }), dir),
      el("td", {}, cat),
      el("td", { class: "num" }, el("input", { value: t.amount_usd, inputmode: "decimal", placeholder: "0.00",
                                               oninput: change("amount_usd") })),
      el("td", {}, payer),
      el("td", {}, el("button", { class: "del", title: "Sil", onclick: () => {
        txns.splice(i, 1); renderTxns(); scheduleSave();
      } }, "✕")));
    tbody.append(tr);
  });
  updateTxnSummary();
}

function updateTxnSummary() {
  const n = state.transactions.length;
  const r = state.transactions.filter(txnNeedsReview).length;
  $("#txn-summary").textContent = `${n} işlem` + (r ? ` · ${r} tanesi kontrol bekliyor` : "");
}

$("#add-txn").addEventListener("click", () => {
  state.transactions.push(newTxn());
  renderTxns();
  scheduleSave();
});
$("#only-review").addEventListener("change", renderTxns);

$("#mercury-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  const msg = $("#import-msg");
  if (!state.owner.name) {
    msg.replaceChildren(alertBox("warn", "Önce 'Ortak' adımında ad soyadı girin; ortakla yapılan transferler buna göre tanınır.", []));
  }
  const csv = await file.text();
  const res = await api("/api/import/mercury", {
    csv, owner_name: state.owner.name || "", tax_year: state.tax_year, existing: state.transactions,
  });
  if (res.error) { msg.replaceChildren(alertBox("error", res.error, [])); return; }
  state.transactions.push(...res.transactions);
  state.transactions.sort((a, b) => a.date.localeCompare(b.date));
  const review = res.transactions.filter(txnNeedsReview).length;
  const info = [
    `${res.transactions.length} işlem eklendi`,
    res.duplicates ? `${res.duplicates} tekrar eden işlem atlandı` : null,
    review ? `${review} işlemin kategorisini kontrol edin (sarı satırlar)` : null,
    ...res.skipped.slice(0, 8).map((s) => `Atlandı: ${s}`),
  ].filter(Boolean);
  msg.replaceChildren(alertBox(review ? "warn" : "ok", "Mercury içe aktarma tamamlandı", info));
  renderTxns();
  scheduleSave();
});

// ------------------------------------------------------------- kontrol
function rowsTable(rows, cols) {
  return el("table", {},
    el("thead", {}, el("tr", {}, cols.map(([, h]) => el("th", {}, h)))),
    el("tbody", {}, rows.map((r) => el("tr", {}, cols.map(([k]) =>
      el("td", { class: k === "value" ? "num" : k === "part" ? "part" : "" }, r[k] ?? "")))))
  );
}

async function runCheck() {
  const res = await api("/api/compute", state);
  const errBox = $("#check-errors"), warnBox = $("#check-warnings"), out = $("#check-result");
  errBox.replaceChildren(); warnBox.replaceChildren(); out.replaceChildren();
  if (res.errors.length) {
    errBox.append(alertBox("error", "Formlar oluşturulmadan önce düzeltilmesi gerekenler:", res.errors));
    $("#loan-questions").classList.add("hidden");
    return res;
  }
  const r = res.result;
  const n = r.numbers;
  $("#loan-questions").classList.toggle("hidden", !(n.has_borrowed || n.has_loaned));
  if (r.warnings.length) warnBox.append(alertBox("warn", "Uyarılar", r.warnings));
  else warnBox.append(alertBox("ok", "Hata yok. Aşağıdaki değerler formlara yazılacak.", []));

  const left = el("div", {},
    el("h3", {}, `Form 5472 — ${r.form_revision}`),
    el("div", { class: "table-wrap" }, rowsTable(r.rows_5472, [["part", "Bölüm"], ["line", "Satır"], ["description", "Alan"], ["value", "Değer"]])));
  const right = el("div", {},
    el("h3", {}, "Pro Forma 1120"),
    el("div", { class: "table-wrap" }, rowsTable(r.rows_1120, [["line", "Alan"], ["description", "Açıklama"], ["value", "Değer"]])),
    el("h3", { style: "margin-top:18px" }, "Defter özeti (formlara girmez)"),
    el("div", { class: "table-wrap" }, rowsTable(Object.entries(r.books).map(([k, v]) => ({ k, value: Number(v).toLocaleString("en-US") })),
      [["k", "Kalem"], ["value", "USD"]])),
    el("h3", { style: "margin-top:18px" }, "Part V eki"),
    el("pre", { style: "white-space:pre-wrap;font-size:12px" }, r.part_v_statement.join("\n")));
  out.append(left, right);
  return res;
}

// ------------------------------------------------------------- formlar
$("#generate").addEventListener("click", async () => {
  const btn = $("#generate");
  btn.disabled = true;
  btn.textContent = "Oluşturuluyor…";
  const out = $("#gen-result");
  try {
    const res = await api("/api/generate", state);
    out.replaceChildren();
    if (res.errors && res.errors.length) {
      out.append(alertBox("error", "Önce 'Kontrol' adımındaki hataları düzeltin:", res.errors));
      return;
    }
    const links = res.files.map((f) => el("a", { href: `/output/${res.year}/${f}`, target: "_blank" }, `📄 ${f}`));
    out.append(alertBox("ok", `Dosyalar oluşturuldu (klasör: output/${res.year}/)`, []), el("div", { class: "files card" }, links));
    if (res.missing.length) out.append(alertBox("warn", "Eksik:", res.missing));
  } finally {
    btn.disabled = false;
    btn.textContent = "PDF formlarını oluştur";
  }
});

// ------------------------------------------------------------- gezinme
function updateNav() {
  const ok = eligible();
  $("#elig-stop").classList.toggle("hidden", ok || !Object.values(state.eligibility).some(Boolean));
  $$("#steps button").forEach((b) => {
    const s = Number(b.dataset.step);
    b.classList.toggle("active", s === step);
    b.disabled = s > 0 && !ok;
  });
  $$(".step").forEach((sec) => sec.classList.toggle("active", Number(sec.dataset.step) === step));
  $("#prev").disabled = step === 0;
  $("#next").disabled = step === 5 || (step === 0 && !ok);
  $("#next").style.visibility = step === 5 ? "hidden" : "visible";
  $("#f1120-missing").classList.toggle("hidden", meta.has_f1120);
}

function go(s) {
  step = s;
  updateNav();
  if (step === 4) runCheck();
  window.scrollTo(0, 0);
}
$("#steps").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b && !b.disabled) go(Number(b.dataset.step));
});
$("#prev").addEventListener("click", () => go(Math.max(0, step - 1)));
$("#next").addEventListener("click", () => go(Math.min(5, step + 1)));
$("#loan-questions").addEventListener("change", () => setTimeout(runCheck, 600));

// ------------------------------------------------------------- başlat
(async function init() {
  meta = await api("/api/meta");
  const sel = $("#year");
  for (let y = meta.default_year + 1; y >= 2018; y--) sel.append(el("option", { value: y }, y));
  sel.value = meta.default_year;
  sel.addEventListener("change", () => { step = 0; loadYear(sel.value); });
  await loadYear(meta.default_year);
})();
