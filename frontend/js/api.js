import { getIdToken } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";
import { 
  collection, 
  query, 
  where, 
  orderBy, 
  onSnapshot 
} from "https://www.gstatic.com/firebasejs/12.7.0/firebase-firestore.js";
import { db } from "./firebase_app.js";

import { state } from "./session.js";


async function authHeaders(forceRefresh = false) {
  if (!state.user) {
    throw new Error("Please sign in first.");
  }

  try {
    const token = await getIdToken(state.user, forceRefresh);
    return {
      Authorization: `Bearer ${token}`,
    };
  } catch (err) {
    console.error("Token Retrieval Error:", err);
    throw new Error("Session expired. Please sign in again.");
  }
}


function triggerLogout() {
  localStorage.removeItem("authToken");
  // We can't easily trigger the Firebase sign out here without importing it
  // and causing circular deps, but clearing the token and redirecting works.
  window.location.href = "/login";
}


async function parseJsonResponse(response, fallbackMessage) {
  if (response.status === 401) {
    triggerLogout();
    throw new Error("Authentication failed. Redirecting...");
  }

  let body = null;
  try {
    body = await response.json();
  } catch (_) {
    body = {};
  }
  if (response.ok && body?.status !== "error") {
    return body;
  }
  throw new Error(body.answer || body.detail || fallbackMessage);
}


export async function fetchProfile(forceRefresh = false) {
  const response = await fetch("/me", {
    headers: await authHeaders(forceRefresh),
  });
  return parseJsonResponse(response, "Could not load profile.");
}


export async function fetchSessions() {
  const response = await fetch("/session-history", {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Could not load sessions.");
}


export async function fetchSessionHistory(sessionId) {
  const response = await fetch(`/session-history/${sessionId}`, {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Could not load session history.");
}


export function subscribeToSessions(uid, callback) {
  if (!uid) return () => {};
  
  const q = query(
    collection(db, "user_chats", uid, "sessions"),
    orderBy("updated_at", "desc")
  );
  
  return onSnapshot(q, (snapshot) => {
    const sessions = snapshot.docs.map(doc => ({
      id: doc.id,
      ...doc.data()
    }));
    callback(sessions);
  }, (error) => {
    console.error("Error listening to sessions:", error);
  });
}


export async function* sendChatStream(message, history = [], sessionId = null) {
  const response = await fetch("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify({ message, history, session_id: sessionId }),
  });
  if (!response.ok) {
     const text = await response.text();
     let obj = null;
     try {
       obj = JSON.parse(text);
     } catch (_) {}
     throw new Error(obj?.answer || obj?.detail || text || "Server error");
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


export async function uploadPdf(file, visibility = "student") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("visibility", visibility);

  const response = await fetch("/upload_pdf", {
    method: "POST",
    headers: await authHeaders(),
    body: formData,
  });
  return parseJsonResponse(response, "Could not upload PDF.");
}

export async function deleteDocument(filename) {
  const response = await fetch(`/documents/${encodeURIComponent(filename)}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Could not delete document.");
}
