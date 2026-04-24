import { onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";

import { auth, authReady } from "./firebase_app.js";
import { routes, goTo } from "./routes.js";
import { setUser, state } from "./session.js";
import { clearProfileCache, clearSessionsCache } from "./cache.js";


function renderUserSummary(user) {
  const userSlot = document.querySelector("#workspace-user");
  if (!userSlot) {
    return;
  }

  userSlot.textContent = user?.email || "No active session";
}


function bindLogout() {
  const buttons = document.querySelectorAll("#logout-button, #logout-button-sidebar, .logout-button-header");
  buttons.forEach(button => {
    button.addEventListener("click", async () => {
      const uid = state.user?.uid;
      clearProfileCache(uid);
      clearSessionsCache(uid);
      
      localStorage.removeItem("authToken");
      
      try {
        await signOut(auth);
      } catch (e) {
        console.warn("Firebase signout failed (Offline?):", e);
      }
      
      setUser(null);
      goTo(routes.login);
    });
  });
}


export async function requireAuth({ onReady } = {}) {
  await authReady;
  bindLogout();

  onAuthStateChanged(auth, async (user) => {
    setUser(user);
    renderUserSummary(user);

    if (!user) {
      goTo(routes.login);
      return;
    }

    if (onReady) {
      await onReady(user);
    }
  });
}


export async function redirectAuthenticatedUser() {
  await authReady;

  onAuthStateChanged(auth, (user) => {
    setUser(user);
    if (user) {
      goTo(routes.dashboard);
    }
  });
}


export function currentUser() {
  return state.user;
}
