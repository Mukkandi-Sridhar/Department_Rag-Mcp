// Smart caching layer for profile, academic data, and sessions
// Eliminates loading skeletons on subsequent visits

const PROFILE_PREFIX = "profile_";
const SESSIONS_PREFIX = "sessions_";
const DEFAULT_TTL_MS = 30 * 60 * 1000; // 30 minutes

function safeGet(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function safeSet(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Graceful fallback if localStorage unavailable
  }
}

function safeRemove(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Graceful fallback
  }
}

function sessionGet(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function sessionSet(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Graceful fallback
  }
}

function sessionRemove(key) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Graceful fallback
  }
}

// Profile cache helpers
export function getCachedProfile(uid) {
  if (!uid) return null;
  const entry = safeGet(PROFILE_PREFIX + uid);
  if (!entry || !entry.timestamp) return null;

  const age = Date.now() - entry.timestamp;
  const isFresh = age < DEFAULT_TTL_MS;

  return {
    data: entry.data,
    isFresh,
    age,
  };
}

export function setCachedProfile(uid, data) {
  if (!uid) return;
  safeSet(PROFILE_PREFIX + uid, {
    data,
    timestamp: Date.now(),
  });
}

export function clearProfileCache(uid) {
  if (!uid) {
    // Clear all profile caches
    try {
      Object.keys(localStorage)
        .filter((k) => k.startsWith(PROFILE_PREFIX))
        .forEach((k) => localStorage.removeItem(k));
    } catch {
      // ignore
    }
    return;
  }
  safeRemove(PROFILE_PREFIX + uid);
}

// Session history cache helpers (sessionStorage for per-tab recents)
export function getCachedSessions(uid) {
  if (!uid) return null;
  const entry = sessionGet(SESSIONS_PREFIX + uid);
  return entry?.data || null;
}

export function setCachedSessions(uid, sessions) {
  if (!uid || !sessions) return;
  sessionSet(SESSIONS_PREFIX + uid, {
    data: sessions,
    timestamp: Date.now(),
  });
}

export function clearSessionsCache(uid) {
  if (!uid) {
    try {
      Object.keys(sessionStorage)
        .filter((k) => k.startsWith(SESSIONS_PREFIX))
        .forEach((k) => sessionStorage.removeItem(k));
    } catch {
      // ignore
    }
    return;
  }
  sessionRemove(SESSIONS_PREFIX + uid);
}

// Deep equality check for cache diffing
export function isProfileEqual(a, b) {
  if (!a || !b) return false;
  return (
    a.email === b.email &&
    a.role === b.role &&
    a.reg_no === b.reg_no &&
    (a.academic?.name || "") === (b.academic?.name || "") &&
    (a.academic?.cgpa || 0) === (b.academic?.cgpa || 0) &&
    (a.academic?.backlogs || 0) === (b.academic?.backlogs || 0) &&
    (a.academic?.placement || "") === (b.academic?.placement || "")
  );
}
