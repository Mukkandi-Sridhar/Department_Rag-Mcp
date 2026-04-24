import { fetchProfile } from "./api.js";
import { requireAuth } from "./shell.js";
import { currentUid } from "./session.js";
import {
  getCachedProfile,
  setCachedProfile,
  isProfileEqual,
} from "./cache.js";

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) {
    element.textContent = value || "";
  }
}

function renderProfile(profile) {
  setText("#p-name", profile.academic?.name || "Academic User");
  setText("#p-email", profile.email || "No email linked");
  setText("#p-reg", profile.reg_no || "Not linked");

  if (profile.role === "student" && profile.academic) {
      const acad = profile.academic;
      
      const cgpa = parseFloat(acad.cgpa || 0).toFixed(2);
      const backlogs = parseInt(acad.backlogs || 0);
      
      setText("#p-cgpa", cgpa);
      setText("#p-backlogs", backlogs);
      setText("#p-placement", acad.placement || "Not Screened");
  }

  // Dynamic metric colors after values are populated
  const cgpaVal = parseFloat(document.querySelector("#p-cgpa")?.textContent || "0");
  const cgpaEl = document.querySelector("#p-cgpa");
  if (cgpaEl) {
    if (cgpaVal > 7.5) cgpaEl.style.color = "#22c55e";
    else if (cgpaVal >= 6) cgpaEl.style.color = "#f59e0b";
    else cgpaEl.style.color = "#ef4444";
  }

  const backlogVal = parseInt(document.querySelector("#p-backlogs")?.textContent || "0", 10);
  const backlogEl = document.querySelector("#p-backlogs");
  if (backlogEl) {
    backlogEl.style.color = backlogVal === 0 ? "#22c55e" : "#ef4444";
  }
}

async function loadProfile() {
  const uid = currentUid();
  const cached = getCachedProfile(uid);

  // INSTANT RENDER: show cached profile immediately if available
  if (cached?.data) {
    renderProfile(cached.data);
  }

  // BACKGROUND REFRESH: fetch fresh data silently
  try {
    const body = await fetchProfile();
    if (body.status === "answered") {
      const freshData = body.data || {};

      // Only update UI if data actually changed from cache
      if (!cached?.data || !isProfileEqual(cached.data, freshData)) {
        renderProfile(freshData);
      }

      // Always update cache with fresh data and timestamp
      setCachedProfile(uid, freshData);
    }
  } catch (error) {
    console.error("Profile load failed:", error);
  }
}

async function initProfile() {
  await requireAuth({
    async onReady(user) {
      loadProfile();
    },
  });

  document.querySelector("#logout-button-alt")?.addEventListener("click", async () => {
    const { auth } = await import("./firebase_app.js");
    await auth.signOut();
    window.location.href = "/login";
  });
}

initProfile();

