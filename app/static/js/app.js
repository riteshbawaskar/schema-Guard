// Shared helpers used across DB Schema Validator UI pages.

async function apiRequest(url, options = {}) {
  const opts = Object.assign({ headers: { "Content-Type": "application/json" } }, options);
  if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
  const resp = await fetch(url, opts);
  let data = null;
  try { data = await resp.json(); } catch (e) { /* no body */ }
  if (!resp.ok) {
    const message = (data && data.detail) ? data.detail : `Request failed (${resp.status})`;
    throw new Error(message);
  }
  return data;
}

function ensureToastContainer() {
  let c = document.getElementById("toastContainer");
  if (!c) {
    c = document.createElement("div");
    c.id = "toastContainer";
    c.className = "toast-container position-fixed bottom-0 end-0 p-3";
    c.style.zIndex = 1080;
    document.body.appendChild(c);
  }
  return c;
}

function showToast(message, variant = "primary") {
  const container = ensureToastContainer();
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${variant} border-0`;
  el.setAttribute("role", "alert");
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  container.appendChild(el);
  const toast = new bootstrap.Toast(el, { delay: 4500 });
  toast.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

function fmtDate(iso) {
  if (!iso) return "-";
  try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
}

function statusBadge(status) {
  return `<span class="badge badge-status-${status}">${status || "-"}</span>`;
}
