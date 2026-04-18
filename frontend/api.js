import { getIdToken } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";

import { state } from "./session.js";


async function authHeaders() {
  if (!state.user) {
    throw new Error("Please sign in first.");
  }

  const token = await getIdToken(state.user);
  return {
    Authorization: `Bearer ${token}`,
  };
}


async function parseJsonResponse(response, fallbackMessage) {
  const body = await response.json();
  if (response.ok) {
    return body;
  }
  throw new Error(body.answer || body.detail || fallbackMessage);
}


export async function fetchProfile() {
  const response = await fetch("/me", {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Could not load profile.");
}


export async function sendChat(message, history = []) {
  const response = await fetch("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify({ message, history }),
  });
  return parseJsonResponse(response, "Could not send chat request.");
}


export async function uploadPdf(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/upload_pdf", {
    method: "POST",
    headers: await authHeaders(),
    body: formData,
  });
  return parseJsonResponse(response, "Could not upload PDF.");
}
