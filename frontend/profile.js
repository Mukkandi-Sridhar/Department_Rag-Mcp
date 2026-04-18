import { fetchProfile } from "./api.js";
import { requireAuth } from "./shell.js";


function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) {
    element.textContent = value || "";
  }
}


function renderProfile(profile) {
  const details = document.querySelector("#profile-details");
  if (!details) {
    return;
  }

  details.innerHTML = `
    <div><strong>Role</strong><span>${profile.role || "-"}</span></div>
    <div><strong>Email</strong><span>${profile.email || "-"}</span></div>
    <div><strong>Register No</strong><span>${profile.reg_no || "-"}</span></div>
    <div><strong>UID</strong><span>${profile.uid || "-"}</span></div>
  `;
}


async function loadProfile() {
  setText("#profile-status", "Loading profile...");

  try {
    const body = await fetchProfile();
    renderProfile(body.data || {});
    setText("#profile-status", body.answer || "Profile loaded.");
  } catch (error) {
    setText("#profile-status", error.message || "Could not load profile.");
  }
}


async function initProfile() {
  await requireAuth({
    async onReady() {
      await loadProfile();
    },
  });
}


initProfile();
