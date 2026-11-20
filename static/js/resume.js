/**
 * resume.js — Drag-and-drop upload + client-side validation
 * Loaded only on resume pages via {% block scripts %}.
 */

(function () {
  "use strict";

  const dropZone   = document.getElementById("dropZone");
  const fileInput  = document.getElementById("resume_file");
  const filePreview = document.getElementById("filePreview");
  const fileName   = document.getElementById("fileName");
  const fileSize   = document.getElementById("fileSize");
  const submitBtn  = document.getElementById("submitBtn");
  const btnText    = document.getElementById("btnText");
  const btnLoading = document.getElementById("btnLoading");
  const valMsg     = document.getElementById("validationMsg");
  const uploadForm = document.getElementById("uploadForm");

  if (!dropZone) return;   // not on upload page

  const ALLOWED = ["application/pdf",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
  const ALLOWED_EXT = [".pdf", ".docx"];
  const MAX_BYTES = 5 * 1024 * 1024;   // 5 MB

  // ---- open file browser when clicking the zone ----
  dropZone.addEventListener("click", (e) => {
    if (e.target.closest("label") || e.target === fileInput) return;
    fileInput.click();
  });

  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });

  // ---- drag events ----
  ["dragenter", "dragover"].forEach(evt =>
    dropZone.addEventListener(evt, (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); }));

  ["dragleave", "drop"].forEach(evt =>
    dropZone.addEventListener(evt, (e) => { e.preventDefault(); dropZone.classList.remove("drag-over"); }));

  dropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer?.files;
    if (files?.length) {
      fileInput.files = files;    // assign to input so form submits it
      _handleFile(files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) _handleFile(fileInput.files[0]);
  });

  function _handleFile(file) {
    // Extension check
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      _showError(`File type "${ext}" is not supported. Please upload a PDF or DOCX.`);
      _resetBtn();
      return;
    }
    // Size check
    if (file.size > MAX_BYTES) {
      _showError(`File is too large (${_fmtSize(file.size)}). Maximum is 5 MB.`);
      _resetBtn();
      return;
    }
    _clearError();
    fileName.textContent = file.name;
    fileSize.textContent = _fmtSize(file.size);
    filePreview.classList.remove("d-none");
    submitBtn.disabled = false;
  }

  // ---- show loading state on submit ----
  uploadForm?.addEventListener("submit", (e) => {
    if (submitBtn.disabled) { e.preventDefault(); return; }
    btnText.classList.add("d-none");
    btnLoading.classList.remove("d-none");
    submitBtn.disabled = true;
  });

  function _fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function _showError(msg) {
    if (!valMsg) return;
    valMsg.textContent = msg;
    valMsg.classList.remove("d-none");
  }

  function _clearError() {
    if (!valMsg) return;
    valMsg.textContent = "";
    valMsg.classList.add("d-none");
  }

  function _resetBtn() {
    if (!submitBtn) return;
    submitBtn.disabled = true;
    filePreview?.classList.add("d-none");
  }

})();
