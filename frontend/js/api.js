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


export async function* sendChatStream(message, history = []) {
  const response = await fetch("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify({ message, history }),
  });
  if (!response.ok) {
     let text = await response.text();
     try {
       const obj = JSON.parse(text);
       throw new Error(obj.answer || obj.detail || "Server error");
     } catch (e) {
       throw new Error("Server error: " + text);
     }
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    
    // Server-Sent Events structure: 'data: {...}\n\n'
    const payloadSeparator = "\n\n";
    let index;
    
    while ((index = buffer.indexOf(payloadSeparator)) !== -1) {
      const chunk = buffer.slice(0, index);
      buffer = buffer.slice(index + payloadSeparator.length);
      
      if (chunk.trim() !== "") {
        if (chunk.startsWith("data: ")) {
          try {
            const dataStr = chunk.slice(6);
            const parsed = JSON.parse(dataStr);
            yield parsed;
          } catch (e) {
            console.error("Failed parsing SSE chunk", e, chunk);
          }
        }
      }
    }
  }
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
