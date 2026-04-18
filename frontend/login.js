import {
  signInWithEmailAndPassword,
} from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";

import { auth, authReady } from "./firebase_app.js";
import { routes, goTo } from "./routes.js";
import { redirectAuthenticatedUser } from "./shell.js";


function setStatus(message) {
  const status = document.querySelector("#auth-status");
  if (status) {
    status.textContent = message || "";
  }
}


async function handleLogin(event) {
  event.preventDefault();

  const email = document.querySelector("#email")?.value.trim() || "";
  const password = document.querySelector("#password")?.value || "";

  setStatus("Signing in...");

  try {
    await authReady;
    await signInWithEmailAndPassword(auth, email, password);
    setStatus("Signed in successfully. Redirecting...");
    goTo(routes.dashboard);
  } catch (error) {
    setStatus(error.message || "Sign-in failed.");
  }
}


function initLoginPage() {
  const form = document.querySelector("#login-form");
  if (form) {
    form.addEventListener("submit", handleLogin);
  }

  redirectAuthenticatedUser();
}


initLoginPage();
