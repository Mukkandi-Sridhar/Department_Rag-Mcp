import { sendChatStream } from "./api.js";
import { requireAuth } from "./shell.js";

const conversation = [];
const STORAGE_KEY = "department_ai_dashboard_conversation";

// Configure marked with highlight.js for the Code Block spec
if (window.marked) {
  const renderer = new marked.Renderer();
  
  // 8. Code Block Component Implementation
  renderer.code = (code, lang) => {
    const validLang = lang || 'text';
    const highlighted = window.hljs ? hljs.highlightAuto(code).value : code;
    return `
      <div class="code-block-container">
        <div class="code-block-header">
          <span class="code-lang">${validLang}</span>
          <button class="copy-btn" onclick="copyToClipboard(this, \`${btoa(code)}\`)">
            <i class="far fa-copy"></i> Copy code
          </button>
        </div>
        <div class="code-block-body">
          <pre><code class="hljs language-${validLang}">${highlighted}</code></pre>
        </div>
      </div>
    `;
  };

  marked.setOptions({
    renderer,
    breaks: true,
    gfm: true
  });
}

// Global copy helper for code blocks
window.copyToClipboard = (btn, base64Code) => {
  const code = atob(base64Code);
  navigator.clipboard.writeText(code).then(() => {
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
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
  const snapshot = conversation
    .filter((message) => !message.pending)
    .map((message) => ({
      role: message.role,
      text: message.text,
      meta: message.meta || null,
    }));
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
}

function loadConversation() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return;
    conversation.length = 0;
    for (const item of parsed) {
      if (!item?.text) continue;
      conversation.push({
        id: crypto.randomUUID(),
        role: item.role,
        text: item.text,
        meta: item.meta || null,
      });
    }
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
  }
}

function autoResizeComposer() {
  const question = document.querySelector("#question");
  if (!question) return;
  question.style.height = "auto";
  question.style.height = `${Math.min(question.scrollHeight, 200)}px`;
}

function scrollConversationToBottom() {
  const feed = document.querySelector("#conversation-feed");
  if (!feed) return;
  feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
}

// 7.3 & 7.4 Rendering logic
function renderConversation() {
  const thread = document.querySelector("#chat-thread");
  const welcome = document.querySelector("#welcome-screen");
  if (!thread) return;

  // Hide or show welcome screen
  if (welcome) {
    welcome.style.display = conversation.length > 0 ? "none" : "flex";
  }

  // Clear only messages (keep welcome screen which is handled by display style)
  thread.querySelectorAll(".message-row").forEach(n => n.remove());
  
  conversation.forEach(msg => {
    const row = document.createElement("div");
    row.className = `message-row ${msg.role === 'user' ? 'user-row' : 'assistant-row'}`;

    if (msg.role === 'user') {
      row.innerHTML = `<div class="user-bubble">${msg.text}</div>`;
    } else {
      const htmlContent = marked.parse(msg.text || "");
      row.innerHTML = `
        <div class="assistant-avatar">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" fill="#676767"/>
            <path d="M12 8V16M8 12H16" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="assistant-content">
          ${htmlContent}${msg.pending ? '<span class="streaming-cursor"></span>' : ''}
        </div>
      `;
    }
    thread.appendChild(row);
  });

  saveConversation();
  scrollConversationToBottom();
}

function setComposerActive(isActive) {
  const btn = document.querySelector("#send-button");
  if (btn) {
    if (isActive) btn.classList.add("active");
    else btn.classList.remove("active");
  }
}

async function handleChat(event) {
  event.preventDefault();
  const input = document.querySelector("#question");
  const text = input?.value.trim() || "";
  if (!text) return;

  // Add User Message
  conversation.push({ id: crypto.randomUUID(), role: "user", text });
  
  // Add Pending Assistant Message
  const pendingMsg = { id: crypto.randomUUID(), role: "assistant", text: "", pending: true };
  conversation.push(pendingMsg);

  if (input) input.value = "";
  autoResizeComposer();
  setComposerActive(false);
  renderConversation();

  try {
    const history = conversation.slice(0, -2).map(m => ({ role: m.role, content: m.text }));
    
    // 3.4 Streaming Text Animation
    for await (const chunk of sendChatStream(text, history.slice(-10))) {
      if (chunk.type === "chunk") {
        pendingMsg.text += chunk.content;
        renderConversation();
      } else if (chunk.type === "error") {
        throw new Error(chunk.content);
      }
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

function setupInteractions() {
  const form = document.querySelector("#chat-form");
  const input = document.querySelector("#question");
  const userRow = document.querySelector("#user-profile-row");
  const userMenu = document.querySelector("#user-menu");

  if (form) form.addEventListener("submit", handleChat);
  
  if (input) {
    input.addEventListener("input", () => {
      autoResizeComposer();
      setComposerActive(input.value.trim() !== "");
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form?.requestSubmit();
      }
    });
  }

  // User Profile Menu Toggle
  if (userRow && userMenu) {
    userRow.onclick = (e) => {
      e.stopPropagation();
      userMenu.style.display = userMenu.style.display === "none" ? "block" : "none";
    };
    document.addEventListener("click", () => { userMenu.style.display = "none"; });
  }

  // Header Scroll Effect
  const feed = document.querySelector("#conversation-feed");
  const header = document.querySelector("#main-header");
  if (feed && header) {
    feed.onscroll = () => {
      if (feed.scrollTop > 10) header.classList.add("scrolled");
      else header.classList.remove("scrolled");
    };
  }
  
  // New Chat Button
  document.querySelector("#new-chat-button")?.addEventListener("click", () => {
    conversation.length = 0;
    sessionStorage.removeItem(STORAGE_KEY);
    renderConversation();
    input?.focus();
  });
}

function setupStarterGrid() {
  const grid = document.querySelector("#starter-grid");
  if (!grid) return;
  
  const starters = [
    { title: "Academic records", prompt: "Do I have any backlogs?" },
    { title: "Performance", prompt: "What is my current CGPA?" },
    { title: "Career Readiness", prompt: "Am I ready for placements?" },
    { title: "Department PDFs", prompt: "Search department documents for..." }
  ];

  grid.innerHTML = starters.map(s => `
    <div class="starter-chip" onclick="fillPrompt('${s.prompt}')">
      <span>${s.title}</span>
    </div>
  `).join("");
}

window.fillPrompt = (text) => {
  const input = document.querySelector("#question");
  if (input) {
    input.value = text;
    input.focus();
    autoResizeComposer();
    setComposerActive(true);
  }
};

async function init() {
  loadConversation();
  setupInteractions();
  setupStarterGrid();
  renderConversation();

  // Auth & Profile Init
  requireAuth({
    async onReady(user) {
      if (!user) return;
      setText("#user-initials", "SR");
      setText("#user-display-name", "Sridhar Royal");
      
      const token = await user.getIdToken();
      const res = await fetch("/me", { headers: { "Authorization": `Bearer ${token}` } });
      if (res.ok) {
        const profile = await res.json();
        if (profile.data?.name) setText("#user-display-name", profile.data.name);
      }
    }
  });

  document.querySelector("#logout-button")?.addEventListener("click", async () => {
    const { auth } = await import("./firebase_app.js");
    await auth.signOut();
    window.location.href = "/login";
  });
}

init();


