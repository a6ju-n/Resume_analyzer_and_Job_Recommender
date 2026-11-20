document.getElementById("menuBtn")?.addEventListener("click", () =>
  document.getElementById("sidebar").classList.toggle("open"));

// Helper: fetch with CSRF token.
window.csrfFetch = (url, opts = {}) => {
  const token = document.querySelector('meta[name="csrf-token"]').content;
  opts.headers = { ...(opts.headers || {}), "X-CSRFToken": token };
  return fetch(url, opts);
};
