(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const apiBase = String(window.MERCHANT_AI_API_BASE || document.body.dataset.apiBase || "").replace(/\/$/, "");
  const toast = $("toast");
  let toastTimer = null;

  const clamp = (value, lower, upper) => Math.max(lower, Math.min(upper, value));
  const text = (value, fallback = "—") => value === undefined || value === null || value === "" ? fallback : String(value);
  const pretty = (value) => text(value, "value").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  const json = (value) => { try { return JSON.stringify(value, null, 2); } catch (_error) { return String(value); } };

  function node(tag, className = "", content) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined) element.textContent = content;
    return element;
  }

  function showToast(message, kind = "info") {
    if (toastTimer) window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle("is-error", kind === "error");
    toast.hidden = false;
    toastTimer = window.setTimeout(() => { toast.hidden = true; }, 4700);
  }

  async function request(path, options = {}) {
    const config = { method: options.method || "GET", headers: { Accept: "application/json" } };
    if (options.body !== undefined) {
      config.headers["Content-Type"] = "application/json";
      config.body = JSON.stringify(options.body);
    }
    let response;
    try {
      response = await fetch(`${apiBase}${path}`, config);
    } catch (_error) {
      throw new Error("The API could not be reached. Check the deployed backend and try again.");
    }
    const contentType = response.headers.get("content-type") || "";
    let data = null;
    try { data = contentType.includes("application/json") ? await response.json() : await response.text(); } catch (_error) { /* response error handled below */ }
    if (!response.ok) throw new Error(text(data && (data.error || data.message || data.detail), `Request failed with status ${response.status}.`));
    return data;
  }

  function setBusy(output, button, busy) {
    output.setAttribute("aria-busy", String(busy));
    button.disabled = busy;
  }

  function header(eyebrow, title, state, stateClass = "") {
    const wrap = node("div", "output-topline");
    const copy = node("div");
    copy.append(node("p", "eyebrow", eyebrow), node("h3", "", title));
    wrap.append(copy, node("span", `run-state${stateClass ? ` ${stateClass}` : ""}`, state));
    return wrap;
  }

  function cell(label, value) {
    const item = node("div", "decision-cell");
    item.append(node("small", "", label), node("strong", "", value));
    return item;
  }

  function itemText(value) {
    if (typeof value === "string") return value;
    if (!value || typeof value !== "object") return text(value, "No detail supplied.");
    const title = value.title || value.label || value.signal || value.type || value.name || value.source;
    const detail = value.detail || value.description || value.reason || value.value || value.message || value.status || value.assumption;
    return [title, detail].filter(Boolean).join(": ") || json(value);
  }

  function riskClass(level) {
    if (/CRITICAL/.test(level)) return "risk-critical";
    if (/HIGH/.test(level)) return "risk-high";
    if (/MEDIUM/.test(level)) return "risk-medium";
    if (/LOW/.test(level)) return "risk-low";
    return "risk-neutral";
  }

  function renderFraud(data) {
    const output = $("fraudOutput");
    const score = Number(data && data.risk_score);
    const confidence = Number(data && data.confidence);
    const level = text(data && data.risk_level, "INSUFFICIENT_EVIDENCE").toUpperCase();
    const evidence = Array.isArray(data && data.evidence) ? data.evidence : [];
    output.replaceChildren();
    output.append(header("Decision record", text(data && data.transaction_id, "Synthetic transaction"), "Complete", "is-complete"));

    const summary = node("div", "risk-summary");
    const orb = node("div", `risk-orb ${riskClass(level)}`);
    orb.append(node("span", "", Number.isFinite(score) ? String(Math.round(clamp(score, 0, 100))) : "—"), node("small", "", "risk score"));
    const copy = node("div", "risk-summary-copy");
    copy.append(
      node("p", "response-label", "Recommended action"),
      node("strong", "risk-action", text(data && data.recommended_action, "ESCALATE")),
      node("p", "", text(data && data.reasoning_summary, "INSUFFICIENT_EVIDENCE: the backend did not return a complete audit summary."))
    );
    summary.append(orb, copy);
    output.append(summary);

    const grid = node("div", "decision-grid");
    grid.append(
      cell("Risk level", level),
      cell("Confidence", Number.isFinite(confidence) ? `${Math.round(clamp(confidence <= 1 ? confidence * 100 : confidence, 0, 100))}%` : "—"),
      cell("Case created", data && data.case_created ? "Yes" : "No"),
      cell("Human approval", data && data.human_approval_required ? "Required" : "Not required")
    );
    output.append(grid);

    const section = node("section", "evidence-section");
    section.append(node("p", "response-label", "Evidence reviewed"));
    const list = node("div", "evidence-list");
    if (evidence.length) {
      evidence.slice(0, 8).forEach((entry, index) => {
        const row = node("div", "evidence-item");
        row.append(node("span", "evidence-index", String(index + 1).padStart(2, "0")), node("p", "", itemText(entry)));
        list.append(row);
      });
    } else {
      list.append(node("p", "empty-copy", "No evidence was returned. Treat this result as INSUFFICIENT_EVIDENCE."));
    }
    section.append(list);
    output.append(section);
    const raw = node("details", "raw-details");
    raw.append(node("summary", "", "View strict JSON result"), node("pre", "", json(data)));
    output.append(raw);
  }

  function renderFraudLoading(title, state, stateClass, message) {
    const output = $("fraudOutput");
    output.replaceChildren(header("Decision record", title, state, stateClass), node("p", `output-waiting${stateClass === "is-error" ? " is-error-copy" : ""}`, message));
  }

  function bindFraud() {
    const form = $("fraudForm");
    const output = $("fraudOutput");
    const button = $("runFraudButton");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = { transaction_id: $("transactionSelect").value, untrusted_context: $("fraudContext").value.trim() };
      setBusy(output, button, true);
      renderFraudLoading("Retrieving policy-bound evidence", "Running", "is-running", "Retrieving synthetic transaction, customer, device, merchant, blacklist, velocity, geography, behavioral, and model-risk evidence.");
      try {
        renderFraud(await request("/api/fraud/investigate", { method: "POST", body: payload }));
      } catch (error) {
        renderFraudLoading("Investigation could not run", "Error", "is-error", error.message);
        showToast(error.message, "error");
      } finally {
        setBusy(output, button, false);
      }
    });
  }

  function appendCompactList(container, values, emptyText) {
    if (!Array.isArray(values) || !values.length) {
      container.append(node("p", "empty-copy", emptyText));
      return;
    }
    values.slice(0, 5).forEach((value) => container.append(node("p", "compact-item", itemText(value))));
  }

  function recommendation(item, index) {
    const card = node("article", "recommendation-card");
    const top = node("div", "recommendation-topline");
    top.append(node("span", "recommendation-index", String(index + 1).padStart(2, "0")), node("strong", "", text(item && item.title, "Prioritized recommendation")));
    top.append(node("span", `approval-chip${item && item.requires_approval ? " is-required" : ""}`, item && item.requires_approval ? "Approval required" : "No publish action"));
    card.append(top, node("p", "recommendation-action", text(item && item.action, "No action returned.")));
    const details = node("div", "recommendation-detail-grid");
    const confidence = Number(item && item.confidence);
    details.append(
      cell("Expected impact", text(item && item.expected_impact)),
      cell("Estimated cost", text(item && item.estimated_cost)),
      cell("Risk", text(item && item.risk)),
      cell("Confidence", Number.isFinite(confidence) ? `${Math.round(clamp(confidence <= 1 ? confidence * 100 : confidence, 0, 100))}%` : "—")
    );
    card.append(details);
    return card;
  }

  function renderGrowth(data) {
    const output = $("growthOutput");
    const metrics = data && data.observed_metrics && typeof data.observed_metrics === "object" ? data.observed_metrics : {};
    const recommendations = Array.isArray(data && data.recommendations) ? data.recommendations.slice(0, 3) : [];
    output.replaceChildren();
    output.append(header("Recommendation record", text(data && data.merchant_id, "Merchant workspace"), "Complete", "is-complete"));
    const overview = node("div", "growth-overview");
    overview.append(node("p", "response-label", text(data && data.period, "Reporting window")), node("p", "growth-summary-copy", text(data && data.summary, "No verified summary was returned.")));
    output.append(overview);

    const metricSection = node("section", "metrics-section");
    metricSection.append(node("p", "response-label", "Observed metrics"));
    const metricGrid = node("div", "metrics-grid");
    const entries = Object.entries(metrics);
    if (entries.length) entries.slice(0, 8).forEach(([key, value]) => metricGrid.append(cell(pretty(key), typeof value === "object" ? itemText(value) : text(value))));
    else metricGrid.append(node("p", "empty-copy", "No verified metrics were returned. Recommendations should be treated as limited."));
    metricSection.append(metricGrid);
    output.append(metricSection);

    const recSection = node("section", "recommendations-section");
    recSection.append(node("p", "response-label", "Prioritized recommendations"));
    const recList = node("div", "recommendations-list");
    if (recommendations.length) recommendations.forEach((entry, index) => recList.append(recommendation(entry, index)));
    else recList.append(node("p", "empty-copy", "No recommendation was generated because the available evidence was insufficient."));
    recSection.append(recList);
    output.append(recSection);

    const footnotes = node("div", "growth-footnotes");
    const campaigns = node("div", "growth-footnote");
    campaigns.append(node("p", "response-label", "Draft campaigns"));
    appendCompactList(campaigns, data && data.draft_campaigns, "No draft campaign returned.");
    const limitations = node("div", "growth-footnote");
    limitations.append(node("p", "response-label", "Data limitations"));
    appendCompactList(limitations, data && data.data_limitations, "No data limitations reported.");
    footnotes.append(campaigns, limitations);
    output.append(footnotes);
    const raw = node("details", "raw-details");
    raw.append(node("summary", "", "View strict JSON result"), node("pre", "", json(data)));
    output.append(raw);
  }

  function renderGrowthLoading(title, state, stateClass, message) {
    const output = $("growthOutput");
    output.replaceChildren(header("Recommendation record", title, state, stateClass), node("p", `output-waiting${stateClass === "is-error" ? " is-error-copy" : ""}`, message));
  }

  function bindGrowth() {
    const form = $("growthForm");
    const output = $("growthOutput");
    const button = $("runGrowthButton");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        merchant_id: $("growthMerchantSelect").value,
        period: $("growthPeriod").value,
        untrusted_context: $("growthContext").value.trim()
      };
      setBusy(output, button, true);
      renderGrowthLoading("Retrieving verified merchant metrics", "Running", "is-running", "Reviewing permitted revenue, transactions, average order value, refunds, repeat-customer rate, settlement timing, and payment-method mix.");
      try {
        renderGrowth(await request("/api/growth/recommend", { method: "POST", body: payload }));
      } catch (error) {
        renderGrowthLoading("Advice could not run", "Error", "is-error", error.message);
        showToast(error.message, "error");
      } finally {
        setBusy(output, button, false);
      }
    });
  }

  function bindTabs() {
    const tabs = Array.from(document.querySelectorAll("[role='tab']"));
    const panels = Array.from(document.querySelectorAll("[role='tabpanel']"));
    function activate(tab) {
      tabs.forEach((candidate) => {
        const selected = candidate === tab;
        candidate.classList.toggle("is-active", selected);
        candidate.setAttribute("aria-selected", String(selected));
      });
      panels.forEach((panel) => { panel.hidden = panel.id !== tab.getAttribute("aria-controls"); });
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab));
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = tabs.length - 1;
        tabs[next].focus();
        activate(tabs[next]);
      });
    });
  }

  async function checkHealth(announce = false) {
    const dot = $("healthDot");
    const label = $("healthText");
    dot.className = "status-dot is-pending";
    label.textContent = "Checking API";
    try {
      const data = await request("/api/health");
      dot.className = "status-dot is-online";
      label.textContent = `API ${text(data && data.status, "online")}`;
      $("healthButton").title = json(data);
      if (announce) showToast("Backend health check passed.");
    } catch (error) {
      dot.className = "status-dot is-offline";
      label.textContent = "API unavailable";
      $("healthButton").title = error.message;
      if (announce) showToast(error.message, "error");
    }
  }

  const canvas = $("digitCanvas");
  const context = canvas.getContext("2d");
  const gridSize = 8;
  const pixels = new Float32Array(gridSize * gridSize);
  let drawing = false;
  let previousPoint = null;

  function paintCanvas() {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#102b23";
    context.fillRect(0, 0, canvas.width, canvas.height);
    const cellSize = canvas.width / gridSize;
    for (let y = 0; y < gridSize; y += 1) {
      for (let x = 0; x < gridSize; x += 1) {
        const value = pixels[y * gridSize + x];
        if (value <= 0) continue;
        const lightness = Math.round(78 + value * 177);
        context.fillStyle = `rgb(${lightness}, ${Math.min(255, lightness + 1)}, ${Math.max(112, lightness - 48)})`;
        context.fillRect(x * cellSize, y * cellSize, Math.ceil(cellSize), Math.ceil(cellSize));
      }
    }
  }

  function stamp(x, y, strength = 1) {
    for (let dy = -1; dy <= 1; dy += 1) {
      for (let dx = -1; dx <= 1; dx += 1) {
        const targetX = Math.round(x + dx);
        const targetY = Math.round(y + dy);
        if (targetX < 0 || targetX >= gridSize || targetY < 0 || targetY >= gridSize) continue;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance > 1.5) continue;
        const position = targetY * gridSize + targetX;
        pixels[position] = Math.max(pixels[position], clamp(strength * (1 - distance / 2.1), 0, 1));
      }
    }
  }

  function pointerPoint(event) {
    const box = canvas.getBoundingClientRect();
    return { x: clamp(((event.clientX - box.left) / box.width) * gridSize, 0, gridSize - 1), y: clamp(((event.clientY - box.top) / box.height) * gridSize, 0, gridSize - 1) };
  }

  function paintLine(from, to, strength = 1) {
    const steps = Math.max(1, Math.ceil(Math.hypot(to.x - from.x, to.y - from.y) * 2));
    for (let index = 0; index <= steps; index += 1) {
      const ratio = index / steps;
      stamp(from.x + (to.x - from.x) * ratio, from.y + (to.y - from.y) * ratio, strength);
    }
    paintCanvas();
  }

  function loadExampleEight() {
    pixels.fill(0);
    const loops = [
      [{ x: 2, y: 1 }, { x: 5, y: 1 }, { x: 6, y: 2 }, { x: 5, y: 3 }, { x: 2, y: 3 }, { x: 1, y: 2 }],
      [{ x: 2, y: 4 }, { x: 5, y: 4 }, { x: 6, y: 5 }, { x: 5, y: 6 }, { x: 2, y: 6 }, { x: 1, y: 5 }]
    ];
    loops.forEach((shape) => shape.forEach((point, index) => paintLine(point, shape[(index + 1) % shape.length], .95)));
    paintCanvas();
  }

  function renderVision(data) {
    const probabilities = Array.isArray(data && data.probabilities) ? data.probabilities.slice(0, 10).map((value) => clamp(Number(value) || 0, 0, 1)) : [];
    const digit = text(data && (data.digit ?? data.prediction ?? data.class), "—");
    const confidence = Number(data && data.confidence);
    $("predictionDigit").textContent = digit;
    $("predictionLabel").textContent = digit === "—" ? "Inference completed" : `Predicted digit: ${digit}`;
    $("predictionConfidence").textContent = Number.isFinite(confidence) ? `Model confidence: ${Math.round(clamp(confidence <= 1 ? confidence * 100 : confidence, 0, 100))}%. ${text(data.engine, "")}` : "The endpoint returned a prediction without a confidence value.";
    $("visionRaw").textContent = json(data);
    const chart = $("probabilityChart");
    chart.replaceChildren();
    if (!probabilities.length) chart.append(node("p", "chart-placeholder", "The endpoint did not return per-class probabilities for this inference."));
    else {
      const largest = Math.max(...probabilities);
      probabilities.forEach((value, index) => {
        const row = node("div", `probability-row${value === largest ? " is-top" : ""}`);
        const track = node("div", "probability-track");
        const fill = node("div", "probability-fill");
        fill.style.width = `${Math.round(value * 100)}%`;
        track.append(fill);
        row.append(node("strong", "", String(index)), track, node("span", "", `${Math.round(value * 100)}%`));
        chart.append(row);
      });
    }
  }

  function bindVision() {
    const output = document.querySelector(".vision-result");
    const button = $("predictDigitButton");
    paintCanvas();
    canvas.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      drawing = true;
      canvas.setPointerCapture(event.pointerId);
      previousPoint = pointerPoint(event);
      stamp(previousPoint.x, previousPoint.y);
      paintCanvas();
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!drawing) return;
      const nextPoint = pointerPoint(event);
      paintLine(previousPoint, nextPoint);
      previousPoint = nextPoint;
    });
    const stop = () => { drawing = false; previousPoint = null; };
    canvas.addEventListener("pointerup", stop);
    canvas.addEventListener("pointercancel", stop);
    canvas.addEventListener("lostpointercapture", stop);
    $("clearCanvasButton").addEventListener("click", () => { pixels.fill(0); paintCanvas(); });
    $("loadExampleButton").addEventListener("click", loadExampleEight);
    button.addEventListener("click", async () => {
      if (!Array.from(pixels).some((value) => value > .05)) {
        showToast("Draw a digit or load the sample before predicting.", "error");
        return;
      }
      setBusy(output, button, true);
      try {
        renderVision(await request("/api/vision/predict", { method: "POST", body: { pixels: Array.from(pixels).map((value) => Number(value.toFixed(4))) } }));
      } catch (error) {
        showToast(error.message, "error");
      } finally {
        setBusy(output, button, false);
      }
    });
  }

  bindTabs();
  bindFraud();
  bindGrowth();
  bindVision();
  $("healthButton").addEventListener("click", () => checkHealth(true));
  checkHealth(false);
})();
