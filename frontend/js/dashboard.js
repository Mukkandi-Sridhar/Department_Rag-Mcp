import { sendChatStream, fetchSessionHistory, subscribeToSessions, fetchProfile } from "./api.js";
import { requireAuth } from "./shell.js";
import { state, currentUid } from "./session.js";
import {
  getCachedProfile,
  setCachedProfile,
  isProfileEqual,
  getCachedSessions,
  setCachedSessions,
  clearProfileCache,
  clearSessionsCache,
} from "./cache.js";

const conversation = [];
let currentSessionId = null;
let unsubSessions = null;
let lastSessions = []; 
const BASE_STORAGE_KEY = "department_ai_v2_msg_";
function getStorageKey(uid) { return BASE_STORAGE_KEY + (uid || "anon"); }
const STORAGE_KEYS_TO_CLEAR = ["department_ai_v2_msg_", "current_session_id_", "sessions_", "profile_"];

// Global cached role for UI elements
let userRole = "student";

// Configure marked with highlight.js
if (window.marked) {
  const renderer = new marked.Renderer();
  renderer.code = (code, lang) => {
    const validLang = lang || 'text';
    const highlighted = window.hljs ? hljs.highlightAuto(code).value : code;
    return `
      <div class="code-block-container">
        <div class="code-block-header">
          <span class="code-lang">${validLang}</span>
          <button class="copy-btn" onclick="copyToClipboard(this, \`${btoa(code)}\`)">
             Copy code
          </button>
        </div>
        <div class="code-block-body">
          <pre><code class="hljs language-${validLang}">${highlighted}</code></pre>
        </div>
      </div>
    `;
  };
  marked.setOptions({ renderer, breaks: true, gfm: true });
}

window.copyToClipboard = (btn, base64Code) => {
  const code = atob(base64Code);
  navigator.clipboard.writeText(code).then(() => {
    const originalText = btn.innerHTML;
    btn.innerHTML = 'Copied!';
    setTimeout(() => { btn.innerHTML = originalText; }, 2000);
  });
};

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) {
    element.textContent = value || "";
  }
}

function saveConversation() {
  const uid = state.user?.uid;
  if (!uid) return;
  const snapshot = conversation.filter(m => !m.pending).map(m => ({ role: m.role, text: m.text }));
  sessionStorage.setItem(getStorageKey(uid), JSON.stringify(snapshot));
  if (currentSessionId) sessionStorage.setItem(`current_session_id_${uid}`, currentSessionId);
}

function loadConversation(uid) {
  if (!uid) return;
  const raw = sessionStorage.getItem(getStorageKey(uid));
  currentSessionId = sessionStorage.getItem(`current_session_id_${uid}`);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    conversation.length = 0;
    parsed.forEach(item => conversation.push({ id: crypto.randomUUID(), ...item }));
  } catch (e) {}
}

function scrollConversationToBottom() {
  const feed = document.querySelector("#conversation-feed");
  if (feed) feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
}

function getRoleColor(role) {
  if (role === "faculty") return "#3b82f6";
  if (role === "hod") return "#8b5cf6";
  return "#10a37f";
}

function renderSidebarProfile(data) {
  const role = (data.role || "student").toLowerCase();
  userRole = role;

  const name = data.academic?.name || data.name || "Department User";
  setText("#user-display-name", name);

  const nameEl = document.querySelector("#user-display-name");
  if (nameEl) nameEl.classList.remove("user-name-skeleton");

  setText("#user-role-badge", role);

  const avatarEl = document.querySelector("#user-initials");
  if (avatarEl) {
    avatarEl.style.backgroundColor = getRoleColor(role);
    const parts = name.split(" ");
    avatarEl.textContent = (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
  }

  updateEmptyStateGreeting(role);
}

function updateEmptyStateGreeting(role) {
  const greetingEl = document.querySelector("#dynamic-greeting");
  if (!greetingEl) return;
  if (role === "hod") {
    greetingEl.textContent = "What's on the agenda today?";
  } else if (role === "faculty") {
    greetingEl.textContent = "How can I assist you today?";
  } else {
    greetingEl.textContent = "What would you like to know?";
  }
}
function createBrainAvatar(isThinking, size = 28) {
  const stateClass = isThinking ? 'brain-thinking' : 'brain-idle';
  return `
    <div class="brain-avatar" style="width:${size}px; height:${size}px;">
      <svg class="brain-avatar-svg ${stateClass}" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
        <circle class="glow-circle" cx="14" cy="14" r="18" />
        
        <!-- Connections -->
        <path class="brain-path" d="M14 4 L8 10" />
        <path class="brain-path" d="M14 4 L20 10" />
        <path class="brain-path" d="M8 10 L8 18" />
        <path class="brain-path" d="M20 10 L20 18" />
        <path class="brain-path" d="M8 10 L14 21" />
        <path class="brain-path" d="M20 10 L14 21" />
        <path class="brain-path" d="M8 18 L14 26" />
        <path class="brain-path" d="M20 18 L14 26" />
        <path class="brain-path" d="M14 21 L14 26" />

        <!-- Nodes -->
        <circle class="brain-node" cx="14" cy="4" r="1.8" />
        <circle class="brain-node" cx="8" cy="10" r="1.8" />
        <circle class="brain-node" cx="20" cy="10" r="1.8" />
        <circle class="brain-node" cx="8" cy="18" r="1.8" />
        <circle class="brain-node" cx="20" cy="18" r="1.8" />
        <circle class="brain-node" cx="14" cy="21" r="1.8" />
        <circle class="brain-node" cx="14" cy="26" r="1.8" />
      </svg>
    </div>
  `;
}

function renderConversation() {
  const thread = document.querySelector("#chat-thread");
  const welcome = document.querySelector("#welcome-screen");
  const composerArea = document.querySelector("#composer-area");
  const mainView = document.querySelector(".main-view");
  if (!thread) return;

  const isEmpty = conversation.length === 0;
  if (welcome) {
    welcome.style.display = isEmpty ? "flex" : "none";
    if (isEmpty) {
      const logoContainer = welcome.querySelector(".logo-container");
      if (logoContainer && !logoContainer.querySelector(".brain-avatar")) {
        logoContainer.innerHTML = createBrainAvatar(false, 60);
      }
    }
  }
  
  // Transition composer position
  if (composerArea) {
    if (isEmpty) composerArea.classList.add("floating");
    else composerArea.classList.remove("floating");
  }
  if (mainView) {
    if (isEmpty) mainView.classList.add("empty-state-active");
    else mainView.classList.remove("empty-state-active");
  }

  thread.querySelectorAll(".msg-row").forEach(n => n.remove());
  
  conversation.forEach(msg => {
    const row = document.createElement("div");
    row.className = "msg-row";
    const inner = document.createElement("div");
    inner.className = "msg-content";

    if (msg.role === 'user') {
      const avatar = document.createElement("div");
      avatar.className = "msg-avatar user-circle";
      avatar.style.backgroundColor = getRoleColor(userRole);
      avatar.textContent = document.querySelector("#user-initials")?.textContent || "U";
      
      const p = document.createElement("p");
      p.textContent = msg.text || "";
      inner.appendChild(p);
      row.appendChild(inner);
      row.appendChild(avatar);
      row.style.justifyContent = "flex-end";
      row.style.textAlign = "right";
    } else {
      const avatar = document.createElement("div");
      avatar.className = "msg-avatar ai";
      avatar.innerHTML = createBrainAvatar(msg.pending);
      
      if (msg.pending && !msg.text) {
        inner.innerHTML = `<div class="thinking-container"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>`;
      } else {
        const markdownText = msg.text || "";
        if (window.marked) {
          const rawHtml = marked.parse(markdownText);
          if (window.DOMPurify) {
            inner.innerHTML = window.DOMPurify.sanitize(rawHtml);
          } else {
            const p = document.createElement("p");
            p.textContent = markdownText;
            inner.replaceChildren(p);
          }
        } else {
          const p = document.createElement("p");
          p.textContent = markdownText;
          inner.replaceChildren(p);
        }
        if (msg.pending) {
          const cursor = document.createElement("span");
          cursor.className = "blinking-cursor";
          inner.appendChild(cursor);
        }
      }
      row.appendChild(avatar);
      row.appendChild(inner);
    }
    thread.appendChild(row);
  });

  saveConversation();
  scrollConversationToBottom();
}

async function handleChat(e) {
  e.preventDefault();
  const input = document.querySelector("#question");
  const text = input?.value.trim() || "";
  if (!text) return;

  if (!currentSessionId) currentSessionId = crypto.randomUUID();

  conversation.push({ id: crypto.randomUUID(), role: "user", text });
  const pendingMsg = { id: crypto.randomUUID(), role: "assistant", text: "", pending: true };
  conversation.push(pendingMsg);

  if (input) {
    input.value = "";
    input.style.height = "auto";
  }
  const sendButton = document.querySelector("#send-button");
  if (sendButton) {
    sendButton.disabled = true;
    sendButton.classList.remove("ready");
  }
  
  renderConversation();

  try {
    const history = conversation.slice(0, -2).map(m => ({ role: m.role, content: m.text }));
    for await (const chunk of sendChatStream(text, history.slice(-10), currentSessionId)) {
      if (chunk.type === "chunk") {
        pendingMsg.text += chunk.content;
        renderConversation();
      } else if (chunk.type === "error") throw new Error(chunk.content);
    }
    pendingMsg.pending = false;
  } catch (err) {
    pendingMsg.text = `**Error:** ${err.message}`;
    pendingMsg.pending = false;
  } finally {
    renderConversation();
    input?.focus();
  }
}

function refreshHistorySidebar(sessions) {
  if (sessions) lastSessions = sessions;
  const list = document.querySelector("#history-list");
  if (!list) return;

  const uid = currentUid();
  if (uid && sessions) setCachedSessions(uid, sessions);

  if (lastSessions.length === 0) {
    list.innerHTML = `<div style="padding:20px; text-align:center; font-size:12px; color:#676767;">No recent chats</div>`;
    return;
  }
  list.replaceChildren();
  lastSessions.forEach((s) => {
    const item = document.createElement("div");
    item.className = `history-item ${s.id === currentSessionId ? "active" : ""}`;
    item.textContent = s.title || "New Chat";
    item.addEventListener("click", () => window.selectSession(s.id));
    list.appendChild(item);
  });
}

function renderCachedSessions(uid) {
  const cached = getCachedSessions(uid);
  if (cached && cached.length > 0) {
    lastSessions = cached;
    refreshHistorySidebar();
  }
}

window.selectSession = async (id) => {
  if (id === currentSessionId) return;
  const res = await fetchSessionHistory(id);
  if (res.status === "answered") {
    currentSessionId = id;
    conversation.length = 0;
    (res.data || []).forEach(turn => {
      conversation.push({ id: crypto.randomUUID(), role: "user", text: turn.query });
      conversation.push({ id: crypto.randomUUID(), role: "assistant", text: turn.answer });
    });
    renderConversation();
    refreshHistorySidebar();
  }
};

function setupInteractions() {
  const form = document.querySelector("#chat-form");
  const input = document.querySelector("#question");
  const sendBtn = document.querySelector("#send-button");
  const userRow = document.querySelector("#user-profile-row");
  const userMenu = document.querySelector("#user-menu");

  if (form) form.onsubmit = handleChat;
  if (input) {
    input.oninput = () => {
      input.style.height = "auto";
      input.style.height = input.scrollHeight + "px";
      const hasText = input.value.trim() !== "";
      sendBtn.disabled = !hasText;
      if (hasText) sendBtn.classList.add("ready");
      else sendBtn.classList.remove("ready");
    };
    input.onkeydown = (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    };
  }
  if (userRow && userMenu) {
    userRow.onclick = (e) => {
      e.stopPropagation();
      userMenu.style.display = userMenu.style.display === "none" ? "block" : "none";
    };
    document.onclick = () => { userMenu.style.display = "none"; };
  }

  const newChatBtn = document.querySelector("#new-chat-button");
  if (newChatBtn) {
    newChatBtn.onclick = () => {
      currentSessionId = null;
      conversation.length = 0;
      const uid = state.user?.uid;
      if (uid) {
         sessionStorage.removeItem(getStorageKey(uid));
         sessionStorage.removeItem(`current_session_id_${uid}`);
      }
      renderConversation();
      input?.focus();
    };
  }
}

function setupStarterGrid() {
  const grid = document.querySelector("#starter-grid");
  if (!grid) return;
  const starters = [
    { title: "Academic records", prompt: "Do I have any backlogs?" },
    { title: "Performance", prompt: "What is my current CGPA?" },
    { title: "Career Readiness", prompt: "Am I ready for placements?" },
    { title: "Department Documents", prompt: "Search department records for..." }
  ];
  grid.replaceChildren();
  starters.forEach((s) => {
    const chip = document.createElement("div");
    chip.className = "starter-chip";
    chip.style.cssText = "background:var(--bg-composer); border:1px solid var(--border-subtle); padding:10px 16px; border-radius:12px; cursor:pointer; font-size:13px;";
    chip.textContent = s.title;
    chip.addEventListener("click", () => window.fillPrompt(s.prompt));
    grid.appendChild(chip);
  });
}

window.fillPrompt = (text) => {
  const input = document.querySelector("#question");
  if (input) {
    input.value = text;
    input.dispatchEvent(new Event('input'));
    input.focus();
  }
};

async function init() {
  setupInteractions();
  setupStarterGrid();

  requireAuth({
    async onReady(user) {
      if (!user) {
        if (unsubSessions) unsubSessions();
        return;
      }
      loadConversation(user.uid);
      renderConversation();

      const uid = user.uid;
      const cached = getCachedProfile(uid);

      // INSTANT RENDER: show cached profile immediately if available
      if (cached?.data) {
        renderSidebarProfile(cached.data);
        renderCachedSessions(uid);
      }

      // BACKGROUND REFRESH: fetch fresh data silently
      try {
        let profile;
        try {
          profile = await fetchProfile();
        } catch (e) {
          if (e.message.includes("Invalid Firebase token")) {
            console.warn("Stale token detected. Retrying with force refresh...");
            profile = await fetchProfile(true);
          } else {
            throw e;
          }
        }

        if (profile.status === "answered") {
          const freshData = profile.data || {};

          // Only update UI if data actually changed from cache
          if (!cached?.data || !isProfileEqual(cached.data, freshData)) {
            renderSidebarProfile(freshData);
            renderConversation(); // Refresh avatars with color
          }

          // Always update cache with fresh data and timestamp
          setCachedProfile(uid, freshData);
        }

        if (unsubSessions) unsubSessions();
        unsubSessions = subscribeToSessions(user.uid, sessions => refreshHistorySidebar(sessions));
      } catch (e) {
        console.error("Profile Error", e);
        if (e.message.includes("Invalid Firebase token") || e.message.includes("Session expired")) {
           // If even force refresh fails, or we got a session expired error, the user probably needs to log in again
           console.error("Critical Auth failure. Redirecting to login...");
           // Optional: Show a toast or message before redirect
           // window.location.href = "/login";
        }
      }
    }
  });

  document.querySelector("#logout-button")?.addEventListener("click", async () => {
    if (unsubSessions) unsubSessions();
    const uid = currentUid();
    clearProfileCache(uid);
    clearSessionsCache(uid);
    Object.keys(sessionStorage).forEach((key) => {
      if (STORAGE_KEYS_TO_CLEAR.some((prefix) => key.startsWith(prefix))) {
        sessionStorage.removeItem(key);
      }
    });
    const { auth } = await import("./firebase_app.js");
    await auth.signOut();
    window.location.href = "/login";
  });
}

init();
