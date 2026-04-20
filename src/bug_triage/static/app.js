const state = {
  bugs: [],
  selectedBugId: null,
  detail: null,
  activeView: "triage",
  filters: {
    triage: {
      search: "",
      severity: "all",
      platform: "all",
      readiness: "all",
    },
    design: {
      search: "",
      platform: "all",
      planState: "all",
    },
  },
};

let feedbackTimer = null;

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }

  return response.json();
}

function metric(id, value) {
  const target = document.getElementById(id);
  if (target) {
    target.textContent = value;
  }
}

function showFeedback(message, tone = "info", sticky = false) {
  const banner = document.getElementById("feedback-banner");
  if (!banner) {
    return;
  }

  banner.textContent = message;
  banner.className = `feedback-banner ${tone}`.trim();
  banner.classList.remove("hidden");

  if (feedbackTimer) {
    window.clearTimeout(feedbackTimer);
  }

  if (!sticky) {
    feedbackTimer = window.setTimeout(() => {
      banner.classList.add("hidden");
    }, 3200);
  }
}

function renderMetrics(metrics) {
  metric("metric-total", metrics.total_bugs);
  metric("metric-triaged", metrics.triaged_bugs);
  metric("metric-tests", metrics.generated_tests);
  metric("metric-coverage", `${metrics.triage_coverage}%`);
  metric("metric-test-plans", metrics.generated_test_plans || 0);
}

function badge(label, className = "") {
  const token = document.createElement("span");
  token.className = `badge ${className}`.trim();
  token.textContent = label;
  return token;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatCreatedAt(value) {
  if (!value) {
    return "No timestamp";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatDetailContext(bug) {
  const parts = [
    `#${bug.id}`,
    bug.platform ? bug.platform.toUpperCase() : null,
    bug.engine || "Engine not set",
    bug.build_number ? `Build ${bug.build_number}` : "Build not provided",
  ].filter(Boolean);
  return parts.join(" | ");
}

function matchesSearch(bug, search) {
  if (!search) {
    return true;
  }

  const haystack = [
    bug.game_title,
    bug.platform,
    bug.engine,
    bug.title,
    bug.status,
    bug.severity,
    bug.priority,
    bug.component,
    bug.owner_team,
    bug.triage_summary,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return haystack.includes(search.toLowerCase());
}

function triageReadinessMatches(bug, readiness) {
  switch (readiness) {
    case "needs-triage":
      return !bug.triage_summary;
    case "triaged":
      return Boolean(bug.triage_summary);
    case "has-tests":
      return Number(bug.test_candidates || 0) > 0;
    case "needs-tests":
      return Boolean(bug.triage_summary) && Number(bug.test_candidates || 0) === 0;
    default:
      return true;
  }
}

function designPlanMatches(bug, planState) {
  switch (planState) {
    case "has-plan":
      return Boolean(bug.has_test_plan);
    case "needs-plan":
      return !bug.has_test_plan;
    default:
      return true;
  }
}

function getFilteredBugs(view) {
  if (view === "design") {
    const filters = state.filters.design;
    return state.bugs.filter(
      (bug) =>
        matchesSearch(bug, filters.search) &&
        (filters.platform === "all" || bug.platform === filters.platform) &&
        designPlanMatches(bug, filters.planState)
    );
  }

  const filters = state.filters.triage;
  return state.bugs.filter(
    (bug) =>
      matchesSearch(bug, filters.search) &&
      (filters.severity === "all" || bug.severity === filters.severity) &&
      (filters.platform === "all" || bug.platform === filters.platform) &&
      triageReadinessMatches(bug, filters.readiness)
  );
}

function renderViewSwitcher() {
  document.querySelectorAll(".view-toggle").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.activeView);
  });

  document.getElementById("triage-view").classList.toggle("hidden", state.activeView !== "triage");
  document.getElementById("test-design-view").classList.toggle("hidden", state.activeView !== "test-design");
}

function setActiveView(view) {
  state.activeView = view;
  renderViewSwitcher();
}

function createBugCardMarkup(bug) {
  const severityClass = bug.severity ? `severity-${bug.severity}` : "unfilled";
  const planBadgeClass = bug.has_test_plan ? "plan-ready" : "plan-empty";
  return `
    <div class="bug-card-top">
      <div class="card-row">
        <span class="badge">#${bug.id}</span>
        <span class="badge">${escapeHtml(bug.game_title)}</span>
        <span class="badge">${escapeHtml(bug.platform)}</span>
      </div>
      <small>${escapeHtml(formatCreatedAt(bug.created_at))}</small>
    </div>
    <h3>${escapeHtml(bug.title)}</h3>
    <p>${escapeHtml(bug.triage_summary || "No triage recommendation yet. Open the issue and run triage to route it.")}</p>
    <div class="bug-card-footer">
      <span class="badge ${severityClass}">${escapeHtml(bug.severity || "new")}</span>
      <span class="badge">${escapeHtml(bug.priority || "unscored")}</span>
      <span class="badge">${escapeHtml(bug.component || "unclassified")}</span>
      <span class="badge test-count">${bug.test_candidates} tests</span>
      <span class="badge ${planBadgeClass}">${bug.has_test_plan ? "plan ready" : "no plan"}</span>
    </div>
  `;
}

function renderBugListInto(containerId, bugs, emptyMessage) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }

  container.innerHTML = "";

  if (bugs.length === 0) {
    container.innerHTML = `<p class="empty-copy">${escapeHtml(emptyMessage)}</p>`;
    return;
  }

  bugs.forEach((bug) => {
    const card = document.createElement("article");
    card.className = `bug-card ${bug.id === state.selectedBugId ? "active" : ""}`.trim();
    card.innerHTML = createBugCardMarkup(bug);
    card.addEventListener("click", () => selectBug(bug.id));
    container.appendChild(card);
  });
}

function renderQueueMetrics() {
  const triageBugs = getFilteredBugs("triage");
  const designBugs = getFilteredBugs("design");

  metric("queue-visible-count", triageBugs.length);
  metric(
    "queue-needs-triage-count",
    triageBugs.filter((bug) => !bug.triage_summary).length
  );
  metric(
    "queue-high-risk-count",
    triageBugs.filter((bug) => ["critical", "high"].includes(bug.severity)).length
  );

  metric("design-visible-count", designBugs.length);
  metric(
    "design-plan-count",
    designBugs.filter((bug) => bug.has_test_plan).length
  );
  metric(
    "design-needs-plan-count",
    designBugs.filter((bug) => !bug.has_test_plan).length
  );
}

function renderBugLists() {
  renderBugListInto(
    "bug-list",
    getFilteredBugs("triage"),
    "No game bugs match the current queue filters."
  );
  renderBugListInto(
    "design-bug-list",
    getFilteredBugs("design"),
    "No bugs match the current test design filters."
  );
  renderQueueMetrics();
}

function renderEmptyDetail() {
  document.getElementById("detail-title").textContent = "Select a bug";
  document.getElementById("detail-context-line").textContent =
    "Choose an item from the queue to inspect context, route ownership, and generate artifacts.";
  document.getElementById("detail-empty").classList.remove("hidden");
  document.getElementById("detail-content").classList.add("hidden");
  document.getElementById("design-selected-bug").className = "selected-bug-card empty-copy";
  document.getElementById("design-selected-bug").textContent =
    "Select a bug from the library to generate a grouped testcase plan.";
  syncActionButtons();
}

function syncActionButtons() {
  const hasSelection = state.selectedBugId !== null;
  const triageButton = document.getElementById("triage-button");
  const testButton = document.getElementById("test-button");
  const testPlanButton = document.getElementById("test-plan-button");

  if (triageButton && !triageButton.dataset.busy) {
    triageButton.disabled = !hasSelection;
  }
  if (testButton && !testButton.dataset.busy) {
    testButton.disabled = !hasSelection;
  }
  if (testPlanButton && !testPlanButton.dataset.busy) {
    testPlanButton.disabled = !hasSelection;
  }
}

async function loadDashboard(selectMostRecent = false) {
  const [health, dashboard] = await Promise.all([
    fetchJson("/api/health"),
    fetchJson("/api/dashboard"),
  ]);

  document.getElementById("mode-pill").textContent = health.mode;
  document.getElementById("scope-pill").textContent = health.scope;

  state.bugs = dashboard.bugs;
  renderMetrics(dashboard.metrics);

  if (state.bugs.length === 0) {
    state.selectedBugId = null;
    state.detail = null;
    renderBugLists();
    renderEmptyDetail();
    return;
  }

  if (selectMostRecent || state.selectedBugId === null) {
    state.selectedBugId = state.bugs[0].id;
  }

  if (!state.bugs.some((bug) => bug.id === state.selectedBugId)) {
    state.selectedBugId = state.bugs[0].id;
  }

  renderBugLists();
  await loadBugDetail(state.selectedBugId);
  renderBugLists();
}

async function selectBug(bugId) {
  state.selectedBugId = bugId;
  renderBugLists();
  await loadBugDetail(bugId);
}

async function loadBugDetail(bugId) {
  const detail = await fetchJson(`/api/bugs/${bugId}`);
  state.detail = detail;
  renderDetail(detail);
}

function renderDetail(detail) {
  const bug = detail.bug;

  document.getElementById("detail-title").textContent = `${bug.game_title} - ${bug.title}`;
  document.getElementById("detail-context-line").textContent = formatDetailContext(bug);
  document.getElementById("detail-description").textContent = bug.description;

  const badges = document.getElementById("detail-badges");
  badges.innerHTML = "";
  badges.appendChild(badge(`#${bug.id}`));
  badges.appendChild(badge(bug.game_title));
  badges.appendChild(badge(bug.platform));
  badges.appendChild(badge(bug.engine || "unknown-engine"));
  badges.appendChild(badge(bug.severity || "new", bug.severity ? `severity-${bug.severity}` : "unfilled"));
  badges.appendChild(badge(bug.priority || "unscored"));
  badges.appendChild(badge(bug.component || "unclassified"));
  badges.appendChild(badge(bug.owner_team || "unassigned"));

  const meta = document.getElementById("detail-meta");
  meta.innerHTML = "";
  [
    ["Status", bug.status],
    ["Build", bug.build_number || "not provided"],
    ["Environment", bug.environment || "not provided"],
    ["Version", bug.version || "not provided"],
    ["External ID", bug.external_id || "not provided"],
    ["Source", bug.source],
    ["Created", formatCreatedAt(bug.created_at)],
    ["Updated", formatCreatedAt(bug.updated_at)],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "meta-item";
    item.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
    meta.appendChild(item);
  });

  renderTriage(detail.triage);
  renderTests(detail.tests || []);
  renderArtifacts(detail.artifacts || []);
  renderTestPlan(detail.test_plan);
  renderSelectedBugSummary(detail);
  primeTestPlanForm(detail);

  document.getElementById("detail-empty").classList.add("hidden");
  document.getElementById("detail-content").classList.remove("hidden");
  syncActionButtons();
}

function renderSelectedBugSummary(detail) {
  const container = document.getElementById("design-selected-bug");
  if (!container) {
    return;
  }

  if (!detail) {
    container.className = "selected-bug-card empty-copy";
    container.textContent = "Select a bug from the library to generate a grouped testcase plan.";
    return;
  }

  const bug = detail.bug;
  const triageSummary = detail.triage?.summary || "Run triage for stronger routing and testcase context.";
  container.className = "selected-bug-card";
  container.innerHTML = `
    <div class="artifact-meta">
      <span class="badge">#${bug.id}</span>
      <span class="badge">${escapeHtml(bug.game_title)}</span>
      <span class="badge">${escapeHtml(bug.platform)}</span>
      <span class="badge ${bug.severity ? `severity-${bug.severity}` : "unfilled"}">${escapeHtml(bug.severity || "new")}</span>
    </div>
    <strong>${escapeHtml(bug.title)}</strong>
    <p>${escapeHtml(triageSummary)}</p>
    <div class="suite-meta">
      <span class="badge">${escapeHtml(bug.component || "unclassified")}</span>
      <span class="badge">${(detail.artifacts || []).length} artifacts</span>
      <span class="badge">${(detail.tests || []).length} tests</span>
      <span class="badge ${detail.test_plan ? "plan-ready" : "plan-empty"}">${detail.test_plan ? "plan ready" : "plan not generated"}</span>
    </div>
  `;
}

function renderTriage(triage) {
  const container = document.getElementById("triage-block");
  if (!triage) {
    container.className = "triage-block empty-copy";
    container.textContent = "No triage recommendation has been generated yet.";
    return;
  }

  const evidenceItems = triage.evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  container.className = "triage-block";
  container.innerHTML = `
    <p class="body-copy">${escapeHtml(triage.summary)}</p>
    <div class="triage-grid">
      <div><span>Confidence</span><strong>${Math.round(triage.confidence * 100)}%</strong></div>
      <div><span>Duplicate candidate</span><strong>${triage.duplicate_of_id ? `#${triage.duplicate_of_id}` : "none"}</strong></div>
      <div><span>Probable root cause</span><strong>${escapeHtml(triage.probable_root_cause)}</strong></div>
      <div><span>Next action</span><strong>${escapeHtml(triage.next_action)}</strong></div>
    </div>
    <div>
      <span class="section-kicker">Evidence</span>
      <ul class="evidence-list">${evidenceItems}</ul>
    </div>
  `;
}

function renderTests(tests) {
  const container = document.getElementById("tests-block");
  if (!tests || tests.length === 0) {
    container.className = "tests-block empty-copy";
    container.textContent = "No candidate tests have been generated yet.";
    return;
  }

  container.className = "tests-block";
  container.innerHTML = "";

  tests.forEach((test) => {
    const item = document.createElement("article");
    item.className = "test-item";
    item.innerHTML = `
      <div class="test-meta">
        <div><span>Type</span><strong>${escapeHtml(test.test_type)}</strong></div>
        <div><span>Framework</span><strong>${escapeHtml(test.framework)}</strong></div>
        <div><span>Status</span><strong>${escapeHtml(test.status)}</strong></div>
      </div>
      <div class="test-file">
        <span>File path</span>
        <strong>${escapeHtml(test.file_path)}</strong>
      </div>
      <p class="body-copy">${escapeHtml(test.execution_summary)}</p>
      <div class="test-code">
        <pre>${escapeHtml(test.generated_code)}</pre>
      </div>
    `;
    container.appendChild(item);
  });
}

function renderArtifacts(artifacts) {
  const container = document.getElementById("artifact-list");
  if (!artifacts || artifacts.length === 0) {
    container.className = "artifact-list empty-copy";
    container.textContent = "No supporting artifacts attached yet.";
    return;
  }

  container.className = "artifact-list";
  container.innerHTML = "";

  artifacts.forEach((artifact) => {
    const item = document.createElement("article");
    item.className = "artifact-item";
    const excerpt = artifact.extracted_text
      ? `<p>${escapeHtml(artifact.extracted_text.slice(0, 220))}${artifact.extracted_text.length > 220 ? "..." : ""}</p>`
      : "<p>No extracted text preview available for this artifact.</p>";
    item.innerHTML = `
      <div class="artifact-meta">
        <span class="badge">${escapeHtml(artifact.artifact_kind)}</span>
        <span class="badge">${escapeHtml(artifact.mime_type)}</span>
      </div>
      <strong>${escapeHtml(artifact.name)}</strong>
      ${excerpt}
    `;
    container.appendChild(item);
  });
}

function renderTestPlan(testPlan) {
  const container = document.getElementById("test-plan-block");
  if (!testPlan) {
    container.className = "test-plan-block empty-copy";
    container.textContent = "No intelligent testcase plan has been generated yet.";
    return;
  }

  const suitesHtml = testPlan.suites
    .map((suite) => {
      const coverageBadges = (suite.coverage_focus || [])
        .map((item) => `<span class="badge">${escapeHtml(item)}</span>`)
        .join("");

      const casesHtml = (suite.test_cases || [])
        .map(
          (testCase) => `
            <details class="case-item">
              <summary>
                <span>${escapeHtml(testCase.title)}</span>
                <span class="badge">${escapeHtml(testCase.priority)}</span>
              </summary>
              <div class="case-body">
                ${renderCaseBlock("Objective", [testCase.objective], false)}
                ${renderCaseBlock("Preconditions", testCase.preconditions, false)}
                ${renderCaseBlock("Steps", testCase.steps, true)}
                ${renderCaseBlock("Expected results", testCase.expected_results, false)}
                ${renderCaseBlock("Edge cases", testCase.edge_cases, false)}
                ${renderCaseBlock("Tags", testCase.tags, false)}
                ${renderCaseBlock("Automation notes", [testCase.automation_notes], false)}
              </div>
            </details>
          `
        )
        .join("");

      return `
        <article class="suite-card">
          <div class="suite-meta">
            <span class="badge">${escapeHtml(suite.suite_category)}</span>
            ${coverageBadges}
          </div>
          <h4>${escapeHtml(suite.suite_name)}</h4>
          <p>${escapeHtml(suite.purpose)}</p>
          <div class="suite-list">${casesHtml}</div>
        </article>
      `;
    })
    .join("");

  container.className = "test-plan-block";
  container.innerHTML = `
    <article class="suite-card">
      <div class="suite-meta">
        <span class="badge">${escapeHtml(testPlan.feature_goal)}</span>
      </div>
      <p>${escapeHtml(testPlan.summary)}</p>
      ${renderCaseBlock("Assumptions", testPlan.assumptions, false)}
      ${renderCaseBlock("Suggested execution order", testPlan.suggested_execution_order, false)}
      ${renderCaseBlock("Risks not covered", testPlan.risks_not_covered, false)}
    </article>
    <div class="suite-list">${suitesHtml}</div>
  `;
}

function renderCaseBlock(title, items, ordered) {
  if (!items || items.length === 0) {
    return "";
  }

  const tag = ordered ? "ol" : "ul";
  const listHtml = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <div class="case-block">
      <h5>${escapeHtml(title)}</h5>
      <${tag}>${listHtml}</${tag}>
    </div>
  `;
}

function primeTestPlanForm(detail) {
  const form = document.getElementById("test-plan-form");
  if (!form) {
    return;
  }

  if (!form.dataset.seededForBug || form.dataset.seededForBug !== String(detail.bug.id)) {
    form.querySelector('input[name="feature_goal"]').value =
      detail.test_plan?.feature_goal || detail.bug.title;
    form.querySelector('textarea[name="design_notes"]').value =
      detail.test_plan?.design_notes || "";
    form.querySelector('input[name="focus_areas"]').value =
      detail.triage?.component || detail.bug.platform || "";
    form.dataset.seededForBug = String(detail.bug.id);
  }
}

async function runButtonAction(buttonId, busyLabel, task, successMessage) {
  const button = document.getElementById(buttonId);
  const originalText = button.textContent;
  button.dataset.busy = "true";
  button.disabled = true;
  button.textContent = busyLabel;

  try {
    await task();
    if (successMessage) {
      showFeedback(successMessage, "success");
    }
  } catch (error) {
    showFeedback(error.message || "Request failed.", "error", true);
    throw error;
  } finally {
    delete button.dataset.busy;
    button.textContent = originalText;
    syncActionButtons();
  }
}

async function submitBugForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  payload.metadata = { submitted_from: "dashboard" };

  await runButtonAction(
    "create-bug-button",
    "Creating bug...",
    async () => {
      await fetchJson("/api/bugs", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      form.reset();
      form.querySelector('input[name="source"]').value = "manual";
      form.querySelector('select[name="platform"]').value = "mobile";
      form.querySelector('select[name="engine"]').value = "Unity";

      state.activeView = "triage";
      renderViewSwitcher();
      await loadDashboard(true);
    },
    "Bug created and added to the queue."
  );
}

async function runTriage() {
  if (state.selectedBugId === null) {
    return;
  }

  await runButtonAction(
    "triage-button",
    "Running triage...",
    async () => {
      await fetchJson(`/api/bugs/${state.selectedBugId}/triage`, {
        method: "POST",
      });
      await loadDashboard();
    },
    "Triage recommendation updated."
  );
}

async function generateTests() {
  if (state.selectedBugId === null) {
    return;
  }

  await runButtonAction(
    "test-button",
    "Generating test...",
    async () => {
      await fetchJson(`/api/bugs/${state.selectedBugId}/generate-tests`, {
        method: "POST",
      });
      await loadDashboard();
    },
    "Regression candidate generated."
  );
}

async function generateIntelligentTestcases() {
  if (state.selectedBugId === null) {
    return;
  }

  const form = document.getElementById("test-plan-form");
  const featureGoal = form.querySelector('input[name="feature_goal"]').value.trim();
  if (!featureGoal) {
    form.querySelector('input[name="feature_goal"]').focus();
    return;
  }

  const designNotes = form.querySelector('textarea[name="design_notes"]').value.trim();
  const focusAreas = form
    .querySelector('input[name="focus_areas"]')
    .value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  const files = Array.from(document.getElementById("artifact-input").files || []);
  const artifacts = await buildArtifactPayloads(files);

  await runButtonAction(
    "test-plan-button",
    "Generating plan...",
    async () => {
      await fetchJson(`/api/bugs/${state.selectedBugId}/generate-intelligent-testcases`, {
        method: "POST",
        body: JSON.stringify({
          feature_goal: featureGoal,
          design_notes: designNotes,
          focus_areas: focusAreas,
          artifacts,
        }),
      });

      document.getElementById("artifact-input").value = "";
      state.activeView = "test-design";
      renderViewSwitcher();
      await loadDashboard();
    },
    "Intelligent testcase plan generated."
  );
}

async function buildArtifactPayloads(files) {
  const payloads = [];
  for (const file of files.slice(0, 12)) {
    payloads.push(await fileToArtifact(file));
  }
  return payloads;
}

async function fileToArtifact(file) {
  const lowerName = file.name.toLowerCase();
  const mimeType = file.type || inferMimeType(lowerName);

  if (mimeType.startsWith("image/")) {
    return {
      name: file.name,
      artifact_kind: "image",
      mime_type: mimeType,
      data_url: await readFileAsDataUrl(file),
    };
  }

  if (mimeType === "application/pdf" || lowerName.endsWith(".pdf")) {
    return {
      name: file.name,
      artifact_kind: "pdf",
      mime_type: "application/pdf",
      data_url: await readFileAsDataUrl(file),
    };
  }

  if (isTextLikeFile(lowerName, mimeType)) {
    return {
      name: file.name,
      artifact_kind: "text",
      mime_type: mimeType || "text/plain",
      text_content: await file.text(),
    };
  }

  return {
    name: file.name,
    artifact_kind: "other",
    mime_type: mimeType || "application/octet-stream",
    data_url: await readFileAsDataUrl(file),
    description: "Opaque binary artifact uploaded from dashboard.",
  };
}

function inferMimeType(fileName) {
  if (fileName.endsWith(".png")) return "image/png";
  if (fileName.endsWith(".jpg") || fileName.endsWith(".jpeg")) return "image/jpeg";
  if (fileName.endsWith(".webp")) return "image/webp";
  if (fileName.endsWith(".pdf")) return "application/pdf";
  if (fileName.endsWith(".md")) return "text/markdown";
  if (fileName.endsWith(".json")) return "application/json";
  if (fileName.endsWith(".csv")) return "text/csv";
  if (fileName.endsWith(".txt") || fileName.endsWith(".log")) return "text/plain";
  return "application/octet-stream";
}

function isTextLikeFile(fileName, mimeType) {
  return (
    Boolean(mimeType && mimeType.startsWith("text/")) ||
    mimeType === "application/json" ||
    [".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml", ".xml"].some((suffix) =>
      fileName.endsWith(suffix)
    )
  );
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error || new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

function bindFilters() {
  const triageSearch = document.getElementById("triage-search");
  const triageSeverity = document.getElementById("triage-severity-filter");
  const triagePlatform = document.getElementById("triage-platform-filter");
  const triageReadiness = document.getElementById("triage-readiness-filter");
  const designSearch = document.getElementById("design-search");
  const designPlatform = document.getElementById("design-platform-filter");
  const designPlan = document.getElementById("design-plan-filter");

  triageSearch.addEventListener("input", (event) => {
    state.filters.triage.search = event.target.value.trim();
    renderBugLists();
  });
  triageSeverity.addEventListener("change", (event) => {
    state.filters.triage.severity = event.target.value;
    renderBugLists();
  });
  triagePlatform.addEventListener("change", (event) => {
    state.filters.triage.platform = event.target.value;
    renderBugLists();
  });
  triageReadiness.addEventListener("change", (event) => {
    state.filters.triage.readiness = event.target.value;
    renderBugLists();
  });

  designSearch.addEventListener("input", (event) => {
    state.filters.design.search = event.target.value.trim();
    renderBugLists();
  });
  designPlatform.addEventListener("change", (event) => {
    state.filters.design.platform = event.target.value;
    renderBugLists();
  });
  designPlan.addEventListener("change", (event) => {
    state.filters.design.planState = event.target.value;
    renderBugLists();
  });
}

document.getElementById("bug-form").addEventListener("submit", (event) => {
  submitBugForm(event).catch((error) => console.error(error));
});
document.getElementById("triage-button").addEventListener("click", () => {
  runTriage().catch((error) => console.error(error));
});
document.getElementById("test-button").addEventListener("click", () => {
  generateTests().catch((error) => console.error(error));
});
document.getElementById("test-plan-button").addEventListener("click", () => {
  generateIntelligentTestcases().catch((error) => console.error(error));
});
document.querySelectorAll(".view-toggle").forEach((button) => {
  button.addEventListener("click", () => setActiveView(button.dataset.view));
});

bindFilters();
renderViewSwitcher();
syncActionButtons();

loadDashboard().catch((error) => {
  console.error(error);
  showFeedback(error.message || "Failed to load dashboard data.", "error", true);
});
