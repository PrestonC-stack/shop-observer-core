(function () {
  const EXTENSION_SOURCE = "advizme-tekmetric-observer";
  const COOLDOWN_MS = 3000;
  const SCAN_DELAY_MS = 300;
  const MAX_TEXT_LENGTH = 240;

  const lastSentAt = new Map();
  const previousSignals = new Map();
  const previousEstimateLines = new Map();
  const previousRoStatusByRo = new Map();
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

  function parseMoney(value) {
    const match = String(value || "").replace(/,/g, "").match(/\$?\s*(-?\d+(?:\.\d{1,2})?)/);
    return match ? Number(match[1]) : null;
  }

  function parseHours(value) {
    const match = String(value || "").match(/\b(\d+(?:\.\d+)?)\s*(?:hr|hrs|hour|hours|labor)\b/i);
    return match ? Number(match[1]) : null;
  }

  function marginFrom(cost, sellPrice) {
    if (typeof cost !== "number" || typeof sellPrice !== "number" || sellPrice <= 0) return null;
    return Math.round(((sellPrice - cost) / sellPrice) * 10000) / 100;
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

    const pathMatch = url.pathname.match(/(?:repair-orders?|work-orders?|orders?|tickets?|invoices?|ro|estimates?)\/(\d{4,8})/i);
    if (pathMatch) return pathMatch[1];

    const headingText = Array.from(document.querySelectorAll("h1,h2,h3,[data-testid*='header' i],[class*='header' i]"))
      .map(visibleText)
      .filter(Boolean)
      .join(" ");
    const headingMatch = headingText.match(/\b(?:RO|Repair Order|Invoice|Ticket|Estimate)\s*#?\s*(\d{4,8})\b/i);
    if (headingMatch) return headingMatch[1];

    const pageMatch = bodyText().slice(0, 6000).match(/\b(?:RO|Repair Order|Invoice|Ticket|Estimate)\s*#?\s*(\d{4,8})\b/i);
    return pageMatch ? pageMatch[1] : "";
  }

  function candidateElements(selector) {
    return Array.from(document.querySelectorAll(selector))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => visibleText(element));
  }

  function firstDatasetValue(element, names) {
    if (!element || !element.dataset) return "";
    for (const name of names) {
      const value = element.dataset[name];
      if (value) return cleanText(value);
    }
    return "";
  }

  function textAfterLabel(text, labelPattern) {
    const match = text.match(labelPattern);
    return match ? cleanText(match[1] || "") : "";
  }

  function inferPartNumber(text) {
    const labeled = textAfterLabel(text, /\b(?:part\s*#|part\s*number|pn|sku)\s*:?\s*([A-Z0-9][A-Z0-9\-/.]{2,})\b/i);
    if (labeled) return labeled;
    const match = text.match(/\b[A-Z0-9]{2,}[A-Z0-9\-/.]{3,}\b/);
    return match ? match[0] : "";
  }

  function inferLineType(text) {
    if (/\blabor\b|\bhrs?\b|\bhours?\b/i.test(text)) return "labor";
    if (/\bpart\b|\bvendor\b|\bsku\b|\bpn\b|\bordered\b/i.test(text)) return "part";
    return "unknown";
  }

  function inferVendor(text) {
    return textAfterLabel(text, /\bvendor\s*:?\s*([A-Za-z0-9 &.'-]{2,60})/i);
  }

  function extractDescription(element, text) {
    const datasetDescription = firstDatasetValue(element, ["description", "lineDescription", "itemDescription", "name"]);
    if (datasetDescription) return limitedText(datasetDescription);

    const labelSelectors = [
      // Targets explicit item/description fields rendered by TekMetric estimate rows.
      "[data-testid*='description' i]",
      // Targets alternate React test attributes for line item names.
      "[data-test*='description' i]",
      // Targets accessible labels TekMetric may attach to description inputs.
      "[aria-label*='description' i]",
      // Targets class-based description cells in table/list estimate layouts.
      "[class*='description' i]",
      // Targets generic line item name cells.
      "[class*='name' i]"
    ];
    const childText = Array.from(element.querySelectorAll(labelSelectors.join(",")))
      .map(visibleText)
      .find(Boolean);
    if (childText) return limitedText(childText);

    return limitedText(text.replace(/\$[\d,.]+/g, "").replace(/\b\d+(?:\.\d+)?\s*(?:hr|hrs|hour|hours)\b/gi, ""));
  }

  function lineMoneyValues(element, text) {
    const costFromDataset = parseMoney(firstDatasetValue(element, ["cost", "partCost", "unitCost"]));
    const sellFromDataset = parseMoney(firstDatasetValue(element, ["sell", "sellPrice", "salePrice", "price"]));
    const cost = costFromDataset ?? parseMoney(textAfterLabel(text, /\b(?:cost|our cost)\s*:?\s*\$?\s*([\d,.]+)/i));
    const sellPrice = sellFromDataset ?? parseMoney(textAfterLabel(text, /\b(?:sell|sale|price|customer price|total)\s*:?\s*\$?\s*([\d,.]+)/i));
    return { cost, sell_price: sellPrice };
  }

  function lineHours(element, text) {
    const datasetHours = firstDatasetValue(element, ["hours", "laborHours", "quantity"]);
    return parseHours(datasetHours) ?? parseHours(text) ?? null;
  }

  function lineFingerprint(data) {
    return [
      data.description,
      data.part_number,
      data.line_type,
      data.cost,
      data.sell_price,
      data.hours
    ].join("|");
  }

  function lineIdentity(data, index) {
    const base = data.part_number || data.description || `line-${index}`;
    return `${data.line_type}:${base}`.toLowerCase();
  }

  function isLikelyEstimateLine(text) {
    return /\b(estimate|labor|part|parts|subtotal|authorized|declined|vendor|qty|hours?|price|cost|sell)\b/i.test(text) &&
      (/\$[\d,.]+/.test(text) || /\b\d+(?:\.\d+)?\s*(?:hr|hrs|hour|hours)\b/i.test(text) || /\b(part\s*#|part\s*number|sku|vendor)\b/i.test(text));
  }

  function findEstimateLineItems() {
    const selectors = [
      // Targets TekMetric React rows explicitly marked as estimate line items.
      "[data-testid*='estimate-line' i]",
      // Targets alternate data-test estimate line item rows.
      "[data-test*='estimate-line' i]",
      // Targets generic line item test IDs in estimate tables.
      "[data-testid*='line-item' i]",
      // Targets alternate generic line item test attributes.
      "[data-test*='line-item' i]",
      // Targets class-based estimate line row containers.
      "[class*='estimate-line' i]",
      // Targets class-based line item row containers.
      "[class*='line-item' i]",
      // Targets table rows when TekMetric renders estimates as tables.
      "tr",
      // Targets ARIA row layouts used by virtualized React grids.
      "[role='row']"
    ];

    const seen = new Set();
    const rows = [];
    candidateElements(selectors.join(",")).forEach((element) => {
      const text = visibleText(element);
      if (!isLikelyEstimateLine(text)) return;
      const key = text.slice(0, 200);
      if (seen.has(key)) return;
      seen.add(key);
      rows.push({ element, text });
    });

    return rows.map(({ element, text }, index) => {
      const money = lineMoneyValues(element, text);
      const hours = lineHours(element, text);
      const data = {
        description: extractDescription(element, text),
        part_number: inferPartNumber(text),
        cost: money.cost,
        sell_price: money.sell_price,
        hours,
        line_type: inferLineType(text),
        raw_text: limitedText(text)
      };
      data.margin = marginFrom(data.cost, data.sell_price);
      data.identity = lineIdentity(data, index);
      data.fingerprint = lineFingerprint(data);
      return data;
    });
  }

  function findEstimateTotal() {
    const text = bodyText();
    const totalPatterns = [
      /\bestimate\s+total\s*:?\s*\$?\s*([\d,.]+)/i,
      /\btotal\s*:?\s*\$?\s*([\d,.]+)/i,
      /\bauthorized\s+total\s*:?\s*\$?\s*([\d,.]+)/i,
      /\binvoice\s+total\s*:?\s*\$?\s*([\d,.]+)/i
    ];
    for (const pattern of totalPatterns) {
      const value = parseMoney(textAfterLabel(text, pattern));
      if (typeof value === "number") return value;
    }
    return null;
  }

  function findStatusText() {
    const selectors = [
      // Targets explicit status badges in TekMetric's React UI.
      "[data-testid*='status' i]",
      // Targets alternate data-test status badges.
      "[data-test*='status' i]",
      // Targets accessible status controls or labels.
      "[aria-label*='status' i]",
      // Targets class-based status badge/chip components.
      "[class*='status' i]",
      // Targets generic badge components that often hold RO status.
      "[class*='badge' i]",
      // Targets ARIA live/status elements.
      "[role='status']"
    ];
    const candidates = candidateElements(selectors.join(","))
      .map(visibleText)
      .filter((text) => /\b(sent|awaiting approval|approved|authorized|work authorized|invoice|invoiced|posted|estimate|open|closed|complete|parts|repair|progress)\b/i.test(text));
    return limitedText(candidates[0] || "");
  }

  function collectEstimateLineEvents(roNumber) {
    const events = [];
    const roScope = roNumber || "unknown";
    const currentKeys = new Set();
    findEstimateLineItems().forEach((line) => {
      const scopedIdentity = `${roScope}:${line.identity}`;
      currentKeys.add(scopedIdentity);
      const previous = previousEstimateLines.get(scopedIdentity);
      const payload = {
        description: line.description,
        part_number: line.part_number,
        cost: line.cost,
        sell_price: line.sell_price,
        hours: line.hours,
        line_type: line.line_type,
        margin: line.margin
      };
      if (!previous) {
        events.push(["estimate_line_added", `${line.line_type} estimate line detected: ${line.description || line.part_number || "unknown item"}`, payload]);
      } else if (previous !== line.fingerprint) {
        events.push(["estimate_line_modified", `${line.line_type} estimate line changed: ${line.description || line.part_number || "unknown item"}`, payload]);
      }
      previousEstimateLines.set(scopedIdentity, line.fingerprint);
    });

    for (const key of Array.from(previousEstimateLines.keys())) {
      if (key.startsWith(`${roScope}:`) && !currentKeys.has(key)) {
        previousEstimateLines.delete(key);
      }
    }
    return events;
  }

  function collectStatusEvents(roNumber) {
    const events = [];
    const statusText = findStatusText();
    if (!statusText) return events;

    const oldStatus = previousRoStatusByRo.get(roNumber || "unknown") || "";
    if (oldStatus && oldStatus !== statusText) {
      events.push(["ro_status_changed", `RO status changed from ${oldStatus} to ${statusText}`, { old_status: oldStatus, new_status: statusText }]);
    }
    previousRoStatusByRo.set(roNumber || "unknown", statusText);

    if (/\b(sent|awaiting approval)\b/i.test(statusText)) {
      events.push(["estimate_sent", `Estimate status detected: ${statusText}`, { estimate_total: findEstimateTotal() }]);
    }
    if (/\b(approved|authorized|work authorized)\b/i.test(statusText)) {
      events.push(["work_authorized", `Work authorization detected: ${statusText}`, { authorized_total: findEstimateTotal() }]);
    }
    if (/\b(invoice|invoiced|posted)\b/i.test(statusText)) {
      events.push(["invoice_created", `Invoice state detected: ${statusText}`, { invoice_total: findEstimateTotal() }]);
    }
    return events;
  }

  function collectPartsOrderedEvents() {
    return findEstimateLineItems()
      .filter((line) => line.line_type === "part")
      .filter((line) => /\b(ordered|on order|po|purchase order)\b/i.test(line.raw_text || ""))
      .map((line) => [
        "parts_ordered",
        `Part ordered: ${line.part_number || line.description || "unknown part"}`,
        {
          part_number: line.part_number,
          description: line.description,
          vendor: inferVendor(`${line.description} ${line.part_number}`)
        }
      ]);
  }

  function collectSignals(roNumber) {
    return [
      ...collectEstimateLineEvents(roNumber),
      ...collectStatusEvents(roNumber),
      ...collectPartsOrderedEvents()
    ];
  }

  function shouldSend(roNumber, eventType, detail, data) {
    const signalKey = `${roNumber || "unknown"}:${eventType}:${detail}:${JSON.stringify(data || {})}`;
    const previous = previousSignals.get(signalKey);
    if (previous === detail) return false;

    const now = Date.now();
    const cooldownKey = signalKey;
    const last = lastSentAt.get(cooldownKey) || 0;
    if (now - last < COOLDOWN_MS) return false;

    previousSignals.set(signalKey, detail);
    lastSentAt.set(cooldownKey, now);
    return true;
  }

  function sendSignal(eventType, roNumber, detail, data) {
    chrome.runtime.sendMessage({
      source: EXTENSION_SOURCE,
      payload: {
        event_type: eventType,
        ro_number: roNumber,
        detail,
        data: data || {},
        detected_at_iso: new Date().toISOString(),
        page_url: window.location.href
      }
    });
  }

  function scanPage() {
    if (!document.body) return;
    const roNumber = extractRoNumber();
    for (const [eventType, detail, data] of collectSignals(roNumber)) {
      if (shouldSend(roNumber, eventType, detail, data)) {
        sendSignal(eventType, roNumber, detail, data);
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
