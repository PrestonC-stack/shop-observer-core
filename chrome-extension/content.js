(function () {
  const EXTENSION_SOURCE = "advizme-tekmetric-observer";
  const COOLDOWN_MS = 3000;
  const SCAN_DELAY_MS = 300;
  const MAX_TEXT_LENGTH = 240;

  const lastSentAt = new Map();
  const previousSignals = new Map();
  let scanTimer = null;

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function limitedText(value) {
    return cleanText(value).slice(0, MAX_TEXT_LENGTH);
  }

  function visibleText(element) {
    if (!element) return "";
    const style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return "";
    return cleanText(element.innerText || element.textContent || "");
  }

  function bodyText() {
    return cleanText(document.body ? document.body.innerText || "" : "");
  }

  function extractRoNumber() {
    const url = new URL(window.location.href);
    const urlCandidates = [
      url.searchParams.get("ro"),
      url.searchParams.get("roNumber"),
      url.searchParams.get("repairOrder"),
      url.searchParams.get("repair_order"),
      url.searchParams.get("ticket"),
      url.searchParams.get("invoice")
    ].filter(Boolean);

    for (const candidate of urlCandidates) {
      const match = String(candidate).match(/\b\d{4,8}\b/);
      if (match) return match[0];
    }

    const pathMatch = url.pathname.match(/(?:repair-orders?|work-orders?|orders?|tickets?|invoices?|ro)\/(\d{4,8})/i);
    if (pathMatch) return pathMatch[1];

    const headingText = Array.from(document.querySelectorAll("h1,h2,h3,[data-testid*='header' i],[class*='header' i]"))
      .map(visibleText)
      .filter(Boolean)
      .join(" ");
    const headingMatch = headingText.match(/\b(?:RO|Repair Order|Invoice|Ticket)\s*#?\s*(\d{4,8})\b/i);
    if (headingMatch) return headingMatch[1];

    const pageMatch = bodyText().slice(0, 5000).match(/\b(?:RO|Repair Order|Invoice|Ticket)\s*#?\s*(\d{4,8})\b/i);
    return pageMatch ? pageMatch[1] : "";
  }

  function textNearKeyword(pattern, radius = 180) {
    const text = bodyText();
    const match = text.match(pattern);
    if (!match || match.index === undefined) return "";
    const start = Math.max(0, match.index - radius);
    const end = Math.min(text.length, match.index + radius);
    return limitedText(text.slice(start, end));
  }

  function candidateElements(selector) {
    return Array.from(document.querySelectorAll(selector))
      .map(visibleText)
      .filter(Boolean);
  }

  function findStatusSignal() {
    const candidates = candidateElements([
      "[data-testid*='status' i]",
      "[data-test*='status' i]",
      "[aria-label*='status' i]",
      "[class*='status' i]",
      "[class*='badge' i]",
      "[class*='chip' i]",
      "[role='status']"
    ].join(","));
    const statusText = candidates.find((text) => /\b(status|stage|workflow|complete|completed|ready|parts|inspection|estimate|progress|qc|hold)\b/i.test(text));
    return statusText ? limitedText(statusText) : "";
  }

  function findDviCompleteSignal() {
    const text = bodyText();
    if (/\b(DVI|inspection)\b[\s\S]{0,160}\b(complete|completed|signed|finished)\b/i.test(text)) {
      return textNearKeyword(/\b(DVI|inspection)\b[\s\S]{0,160}\b(complete|completed|signed|finished)\b/i);
    }
    return "";
  }

  function findComplaintSignal() {
    const candidates = candidateElements([
      "[data-testid*='complaint' i]",
      "[data-testid*='concern' i]",
      "[data-testid*='code' i]",
      "[data-test*='complaint' i]",
      "[data-test*='concern' i]",
      "[name*='complaint' i]",
      "[name*='concern' i]",
      "[class*='complaint' i]",
      "[class*='concern' i]"
    ].join(","));
    const found = candidates.find((text) => /\b(complaint|concern|code|cause|correction)\b/i.test(text));
    if (found) return limitedText(found);

    const text = bodyText();
    if (/\b(complaint|concern)\b[\s\S]{0,120}\b(code|added|changed|updated)\b/i.test(text)) {
      return textNearKeyword(/\b(complaint|concern)\b[\s\S]{0,120}\b(code|added|changed|updated)\b/i);
    }
    return "";
  }

  function findEstimateSignal() {
    const candidates = candidateElements([
      "[data-testid*='estimate' i]",
      "[data-test*='estimate' i]",
      "[class*='estimate' i]",
      "[aria-label*='estimate' i]",
      "table",
      "[role='row']"
    ].join(","));
    const found = candidates.find((text) => /\b(estimate|line item|labor|parts|subtotal|authorized|declined)\b/i.test(text));
    if (found) return limitedText(found);

    const text = bodyText();
    if (/\bestimate\b[\s\S]{0,180}\b(line item|labor|part|added|modified|updated|authorized|declined)\b/i.test(text)) {
      return textNearKeyword(/\bestimate\b[\s\S]{0,180}\b(line item|labor|part|added|modified|updated|authorized|declined)\b/i);
    }
    return "";
  }

  function collectSignals() {
    return [
      ["dvi_complete", findDviCompleteSignal()],
      ["complaint_code_changed", findComplaintSignal()],
      ["job_status_changed", findStatusSignal()],
      ["estimate_line_item_changed", findEstimateSignal()]
    ].filter(([, detail]) => detail);
  }

  function shouldSend(roNumber, eventType, detail) {
    const signalKey = `${roNumber || "unknown"}:${eventType}`;
    const previous = previousSignals.get(signalKey);
    if (previous === detail) return false;

    const now = Date.now();
    const last = lastSentAt.get(signalKey) || 0;
    if (now - last < COOLDOWN_MS) return false;

    previousSignals.set(signalKey, detail);
    lastSentAt.set(signalKey, now);
    return true;
  }

  function sendSignal(eventType, roNumber, detail) {
    chrome.runtime.sendMessage({
      source: EXTENSION_SOURCE,
      payload: {
        event_type: eventType,
        ro_number: roNumber,
        detail,
        detected_at_iso: new Date().toISOString(),
        page_url: window.location.href
      }
    });
  }

  function scanPage() {
    if (!document.body) return;
    const roNumber = extractRoNumber();
    for (const [eventType, detail] of collectSignals()) {
      if (shouldSend(roNumber, eventType, detail)) {
        sendSignal(eventType, roNumber, detail);
      }
    }
  }

  function scheduleScan() {
    window.clearTimeout(scanTimer);
    scanTimer = window.setTimeout(scanPage, SCAN_DELAY_MS);
  }

  if (document.body) {
    const observer = new MutationObserver(scheduleScan);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "data-testid", "data-test", "aria-label", "value"]
    });
    scheduleScan();
  }
})();
