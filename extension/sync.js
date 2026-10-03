// Runs only on JobPilot itself. Picks up the contact data and answer bank the
// Application Kit leaves for it (frontend/components/ApplicationKit.tsx) and
// keeps a copy in the extension. Never touches the login token.
function store(data) {
  if (data && typeof data === "object" && Array.isArray(data.answers)) {
    chrome.storage.local.set({ autofill: data });
  }
}

try {
  store(JSON.parse(localStorage.getItem("jobpilot_autofill") || "null"));
} catch {
  // Nothing synced yet, or storage blocked.
}

window.addEventListener("message", (e) => {
  if (e.source === window && e.origin === location.origin && e.data?.type === "jobpilot-autofill") {
    store(e.data.data);
  }
});
