import {
  signInWithEmailAndPassword,
} from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";

import { auth, authReady } from "./firebase_app.js";
import { routes, goTo } from "./routes.js";
import { redirectAuthenticatedUser } from "./shell.js";


function setStatus(message, isError = false) {
  const status = document.querySelector("#auth-status");
  if (status) {
    status.textContent = message || "";
    status.className = "auth-status-badge" + (isError ? " error" : " success");
    status.style.display = message ? "block" : "none";
  }
}


async function handleLogin(event) {
  event.preventDefault();

  const emailInput = document.querySelector("#email");
  const passwordInput = document.querySelector("#password");
  const submitButton = event.target.querySelector("button[type='submit']");
  
  let email = emailInput?.value.trim() || "";
  const password = passwordInput?.value || "";

  // Smart Identity Matching: Auto-append domain if user only entered Reg No
  if (email && !email.includes("@")) {
      email = `${email.toLowerCase()}@rgmcet.edu.in`;
  }

  if (!email || !password) {
      setStatus("Please fill in both fields.", true);
      return;
  }

  setStatus("Verifying credentials...");
  if (submitButton) {
      submitButton.disabled = true;
      const btnText = submitButton.querySelector(".btn-text");
      const btnArrow = submitButton.querySelector(".btn-arrow");
      const btnSpinner = submitButton.querySelector(".btn-spinner");
      if (btnText) btnText.textContent = "Signing In";
      if (btnArrow) btnArrow.style.display = "none";
      if (btnSpinner) btnSpinner.style.display = "inline";
  }

  try {
    await authReady;
    await signInWithEmailAndPassword(auth, email, password);
    setStatus("Success! Entering workspace...");
    
    // Smooth transition
    setTimeout(() => {
        goTo(routes.dashboard);
    }, 600);
    
  } catch (error) {
    console.error("Auth Error:", error);
    let friendlyMessage = "Sign-in failed. Please check your credentials.";
    
    if (error.code === "auth/invalid-credential") {
        friendlyMessage = "Incorrect email or password code.";
    } else if (error.code === "auth/network-request-failed") {
        friendlyMessage = "Network error. Please check your connection.";
    } else if (error.code === "auth/too-many-requests") {
        friendlyMessage = "Too many failed attempts. Try again later.";
    }

    setStatus(friendlyMessage, true);
    if (submitButton) {
      submitButton.disabled = false;
      const btnText = submitButton.querySelector(".btn-text");
      const btnArrow = submitButton.querySelector(".btn-arrow");
      const btnSpinner = submitButton.querySelector(".btn-spinner");
      if (btnText) btnText.textContent = "Sign In";
      if (btnArrow) btnArrow.style.display = "inline";
      if (btnSpinner) btnSpinner.style.display = "none";
    }
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
