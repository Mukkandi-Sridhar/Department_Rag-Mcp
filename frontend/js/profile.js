import { fetchProfile } from "./api.js";
import { requireAuth } from "./shell.js";

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
}

async function loadProfile() {
  try {
    const body = await fetchProfile();
    if (body.status === "answered") {
       renderProfile(body.data || {});
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

