const INGEST_URL = "http://localhost:8080/ingest/tekmetric-event";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.source !== "advizme-tekmetric-observer") {
    return false;
  }

  const payload = message.payload || {};
  fetch(INGEST_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Advizme-Source": "chrome-extension"
    },
    body: JSON.stringify(payload)
  })
    .then((response) => {
      if (!response.ok) {
        console.warn("AdvizMe TekMetric Observer ingest failed:", response.status);
      }
      sendResponse({ ok: response.ok, status: response.status });
    })
    .catch((error) => {
      console.warn("AdvizMe TekMetric Observer could not reach local Flask server:", error);
      sendResponse({ ok: false, error: String(error) });
    });

  return true;
});
