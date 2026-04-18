import { initializeApp } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-app.js";
import {
  getAnalytics,
  isSupported,
} from "https://www.gstatic.com/firebasejs/12.7.0/firebase-analytics.js";
import {
  browserLocalPersistence,
  getAuth,
  setPersistence,
} from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";


export const firebaseConfig = {
  apiKey: "AIzaSyDPlsZ8EEULeLC-zkz_eS-U2NGAIOhpV7k",
  authDomain: "deptrag.firebaseapp.com",
  projectId: "deptrag",
  storageBucket: "deptrag.firebasestorage.app",
  messagingSenderId: "366173687269",
  appId: "1:366173687269:web:33ecfd4c03b413761e330c",
  measurementId: "G-5V9F498EQ3",
};

export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const authReady = setPersistence(auth, browserLocalPersistence).catch(() => null);

export const analyticsPromise = isSupported().then((supported) => {
  if (!supported) {
    return null;
  }

  return getAnalytics(app);
});
