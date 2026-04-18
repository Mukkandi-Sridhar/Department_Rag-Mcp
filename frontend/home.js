import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";

import { auth, authReady } from "./firebase_app.js";
import { routes } from "./routes.js";


async function initHome() {
  await authReady;

  onAuthStateChanged(auth, (user) => {
    const workspaceLink = document.querySelector('a[href="/dashboard"]');
    const signInLink = document.querySelector('a[href="/login"]');

    if (workspaceLink) {
      workspaceLink.textContent = user ? "Open Workspace" : "Preview Workspace";
      workspaceLink.href = user ? routes.dashboard : routes.login;
    }

    if (signInLink && user) {
      signInLink.textContent = "Go to Dashboard";
      signInLink.href = routes.dashboard;
    }
  });
}


initHome();
