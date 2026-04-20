import { uploadPdf } from "./api.js";
import { requireAuth } from "./shell.js";

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) {
    element.textContent = value || "";
  }
}

async function handleUpload(event) {
  event.preventDefault();
  const fileInput = document.querySelector("#pdf-file");
  const file = fileInput?.files?.[0];

  if (!file) {
    setText("#upload-status", "Please select a PDF file.");
    return;
  }

  setText("#upload-status", "Processing and indexing document...");
  const btn = document.querySelector("#btn-upload");
  if (btn) btn.disabled = true;

  try {
    const body = await uploadPdf(file);
    setText("#upload-status", body.answer || "Document successfully indexed!");
    
    // Reset UI
    if (fileInput) fileInput.value = "";
    setText("#file-name", "No file selected");
    if (btn) btn.style.display = "none";
  } catch (error) {
    setText("#upload-status", error.message || "Upload failed. Please try again.");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function initDocuments() {
  const form = document.querySelector("#upload-form");
  if (form) {
    form.addEventListener("submit", handleUpload);
  }

  await requireAuth({
    onReady(user) {
      // Logic for session display if needed
    },
  });
}

initDocuments();

