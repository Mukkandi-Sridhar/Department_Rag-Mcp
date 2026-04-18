import { sendChat } from "./api.js";
import { requireAuth } from "./shell.js";


const conversation = [];
const STORAGE_KEY = "department_ai_dashboard_conversation";

// Configure marked with highlight.js
if (window.marked && window.hljs) {
  marked.setOptions({
    highlight: function(code, lang) {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
      return hljs.highlightAuto(code).value;
    },
    breaks: true,
    gfm: true
  });
}


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
      sources: message.sources || [],
      note: message.note || "",
    }));

  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
}


function loadConversation() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return;
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return;
    }

    conversation.length = 0;
    for (const item of parsed) {
      const role = item?.role === "assistant" ? "assistant" : "user";
      const text = String(item?.text || "").trim();
      if (!text) {
        continue;
      }

      conversation.push({
        id: crypto.randomUUID(),
        role,
        text,
        meta: item?.meta || null,
        sources: Array.isArray(item?.sources) ? item.sources : [],
        note: item?.note || "",
      });
    }
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
  }
}


function getQuestionBox() {
  return document.querySelector("#question");
}


function autoResizeComposer() {
  const question = getQuestionBox();
  if (!question) {
    return;
  }

  question.style.height = "auto";
  question.style.height = `${Math.min(question.scrollHeight, 220)}px`;
}


function scrollConversationToBottom() {
  const feed = document.querySelector("#conversation-feed");
  if (!feed) {
    return;
  }

  feed.scrollTo({
    top: feed.scrollHeight,
    behavior: "smooth"
  });
}


function renderConversation() {
  const feed = document.querySelector("#conversation-feed");
  const welcomeCard = document.querySelector("#welcome-card");
  if (!feed) {
    return;
  }

  // Remove existing message rows
  feed.querySelectorAll(".message-row").forEach((node) => node.remove());

  if (welcomeCard) {
    welcomeCard.style.display = conversation.length > 0 ? "none" : "flex";
  }

  for (const message of conversation) {
    const row = document.createElement("article");
    row.className = `message-row ${message.role === "user" ? "message-user-row" : "message-assistant-row"}`;

    const avatar = document.createElement("div");
    avatar.className = `message-avatar message-avatar-${message.role}`;
    avatar.textContent = message.role === "assistant" ? "AI" : "U";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    if (message.role === "assistant") {
      const topline = document.createElement("div");
      topline.className = "message-topline";
      topline.innerHTML = `<strong>Assistant</strong>`;
      if (message.pending) {
        topline.innerHTML += `<span class="message-pending">...thinking</span>`;
      }
      bubble.appendChild(topline);
    }

    const textDiv = document.createElement("div");
    textDiv.className = "message-text";
    
    // Render Markdown for Assistant, plain text for User (for safety/simplicity)
    if (message.role === "assistant") {
      textDiv.innerHTML = marked.parse(message.text || "");
    } else {
      textDiv.textContent = message.text || "";
    }

    bubble.appendChild(textDiv);
    
    row.appendChild(avatar);
    row.appendChild(bubble);
    feed.appendChild(row);
  }

  saveConversation();
  scrollConversationToBottom();
}


function setComposerEnabled(isEnabled) {
  const question = getQuestionBox();
  const sendButton = document.querySelector("#send-button");
  if (question) {
    question.disabled = !isEnabled;
  }
  if (sendButton) {
    sendButton.disabled = !isEnabled;
  }
}


function fillPrompt(prompt) {
  const question = getQuestionBox();
  if (!question) {
    return;
  }

  question.value = prompt;
  autoResizeComposer();
  question.focus();
}


function bindPromptButtons() {
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      fillPrompt(button.getAttribute("data-prompt") || "");
    });
  });
}


function bindNewChat() {
  const button = document.querySelector("#new-chat-button");
  if (!button) {
    return;
  }

  button.addEventListener("click", () => {
    conversation.length = 0;
    sessionStorage.removeItem(STORAGE_KEY);
    renderConversation();
    fillPrompt("");
  });
}


function buildRequestHistory() {
  const history = [];
  for (const message of conversation) {
    if (message.pending) continue;
    if (message.role !== "user" && message.role !== "assistant") continue;
    const content = String(message.text || "").trim();
    if (!content) continue;
    history.push({ role: message.role, content });
  }
  return history.slice(-20);
}


async function handleChat(event) {
  event.preventDefault();
  const questionInput = getQuestionBox();
  const question = questionInput?.value.trim() || "";
  if (!question) return;

  const requestHistory = buildRequestHistory();

  conversation.push({
    id: crypto.randomUUID(),
    role: "user",
    text: question,
  });

  const pendingMessage = {
    id: crypto.randomUUID(),
    role: "assistant",
    text: "Working on it...",
    pending: true,
  };
  conversation.push(pendingMessage);

  renderConversation();
  setComposerEnabled(false);
  if (questionInput) questionInput.value = "";
  autoResizeComposer();

  try {
    const body = await sendChat(question, requestHistory);
    pendingMessage.text = body.answer || "No answer received.";
    pendingMessage.pending = false;
    pendingMessage.meta = body;
  } catch (error) {
    pendingMessage.text = `**Error:** ${error.message}`;
    pendingMessage.pending = false;
  } finally {
    renderConversation();
    setComposerEnabled(true);
    getQuestionBox()?.focus();
  }
}


function bindComposer() {
  const form = document.querySelector("#chat-form");
  const question = getQuestionBox();

  if (form) {
    form.addEventListener("submit", handleChat);
  }

  if (question) {
    question.addEventListener("input", autoResizeComposer);
    question.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form?.requestSubmit();
      }
    });
    autoResizeComposer();
  }
}


async function initDashboard() {
  // 1. Initial UI Render (Instant)
  loadConversation();
  bindComposer();
  bindPromptButtons();
  bindNewChat();
  renderConversation();

  // 2. Background Auth Resolution
  requireAuth({
    onReady(user) {
      setText("#workspace-user", user.email || "Active User");
    },
  }).catch(err => {
    console.warn("Auth background check failed:", err);
    setText("#workspace-user", "Offline Mode");
  });
}


initDashboard();

