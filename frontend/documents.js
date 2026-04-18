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
  const file = document.querySelector("#pdf-file")?.files?.[0];

  if (!file) {
    setText("#upload-status", "Choose a PDF first.");
    return;
  }

  setText("#upload-status", "Uploading PDF...");

  try {
    const body = await uploadPdf(file);
    setText("#upload-status", body.answer || "Upload finished.");
  } catch (error) {
    setText("#upload-status", error.message || "Upload failed.");
  }
}


async function initDocuments() {
  const form = document.querySelector("#upload-form");
  if (form) {
    form.addEventListener("submit", handleUpload);
  }

  await requireAuth({
    onReady(user) {
      setText("#upload-status", `Ready to upload as ${user.email}`);
    },
  });
}


initDocuments();
