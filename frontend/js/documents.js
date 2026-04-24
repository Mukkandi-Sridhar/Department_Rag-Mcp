import { uploadPdf, deleteDocument, fetchProfile } from "./api.js";
import { requireAuth } from "./shell.js";

const STUDENT_BLOCK_MESSAGE = "Only faculty or HOD accounts can upload or change department documents.";
let currentRole = "student";

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) {
    element.textContent = value || "";
  }
}

function isStudentRole() {
  return String(currentRole || "").toLowerCase() === "student";
}

async function handleUpload(event) {
  event.preventDefault();
  if (isStudentRole()) {
    setText("#upload-status", STUDENT_BLOCK_MESSAGE);
    return;
  }

  const fileInput = document.querySelector("#pdf-file");
  const visibilityInput = document.querySelector("#visibility");
  const file = fileInput?.files?.[0];
  const visibility = visibilityInput?.value || "student";

  if (!file) {
    setText("#upload-status", "Please select a PDF file.");
    return;
  }

  setText("#upload-status", "Processing and indexing document...");
  const btn = document.querySelector("#btn-upload");
  if (btn) btn.disabled = true;

  try {
    const body = await uploadPdf(file, visibility);
    setText("#upload-status", body.answer || "Document successfully indexed!");
    
    // Reset UI
    if (fileInput) fileInput.value = "";
  } catch (error) {
    setText("#upload-status", error.message || "Upload failed. Please try again.");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleDelete(event) {
  event.preventDefault();
  if (isStudentRole()) {
    setText("#delete-status", STUDENT_BLOCK_MESSAGE);
    return;
  }

  const filename = (document.querySelector("#delete-file-name")?.value || "").trim();
  if (!filename) {
    setText("#delete-status", "Enter a file name like policy.pdf.");
    return;
  }

  try {
    const body = await deleteDocument(filename);
    setText("#delete-status", body.answer || "Document deleted.");
  } catch (error) {
    setText("#delete-status", error.message || "Delete failed. Please try again.");
  }
}

async function initDocuments() {
  const form = document.querySelector("#upload-form");
  if (form) {
    form.addEventListener("submit", handleUpload);
  }
  const deleteBtn = document.querySelector("#btn-delete-doc");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", handleDelete);
  }

  await requireAuth({
    async onReady() {
      try {
        const body = await fetchProfile();
        currentRole = (body.data?.role || "student").toLowerCase();
      } catch {
        currentRole = "student";
      }

      if (isStudentRole()) {
        setText("#upload-status", STUDENT_BLOCK_MESSAGE);
      } else {
        setText("#upload-status", "");
      }
    },
  });
}

initDocuments();

