const sampleReviews = [
  "This snack tastes amazing and arrived fresh.",
  "The flavor was disappointing and not worth the price.",
  "I love the texture, but the packaging was poor.",
  "Not that good. It felt stale and bland.",
  "Delicious product and I would definitely order again."
];

const reviewInput = document.getElementById("review-input");
const preprocessPreview = document.getElementById("preprocess-preview");
const resultsTableWrap = document.getElementById("results-table-wrap");
const frequencyChart = document.getElementById("frequency-chart");
const summaryReport = document.getElementById("summary-report");
const positiveThemes = document.getElementById("positive-themes");
const negativeThemes = document.getElementById("negative-themes");
const serverStatus = document.getElementById("server-status");

document.getElementById("load-sample-btn").addEventListener("click", () => {
  reviewInput.value = sampleReviews.join("\n");
});

document.getElementById("analyze-all-btn").addEventListener("click", analyzeReviews);
document.getElementById("preprocess-btn").addEventListener("click", analyzeReviews);
document.getElementById("frequency-btn").addEventListener("click", analyzeReviews);
document.getElementById("report-btn").addEventListener("click", analyzeReviews);

document.getElementById("clear-all-btn").addEventListener("click", () => {
  reviewInput.value = "";
  resetUi();
});

document.getElementById("file-input").addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (!file) {
    return;
  }

  const text = await file.text();
  reviewInput.value = parseUploadedText(text).join("\n");
  event.target.value = "";
});

async function checkModelStatus() {
  try {
    const response = await fetch("/api/model-status");
    const data = await response.json();
    renderServerStatus(data.ready, data.message);
  } catch (error) {
    renderServerStatus(false, "Flask server is not reachable yet. Start app.py first.");
  }
}

async function analyzeReviews() {
  const reviews = reviewInput.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (!reviews.length) {
    renderServerStatus(false, "Please enter at least one review.");
    resetUi();
    return;
  }

  renderServerStatus(true, "Analyzing reviews with Flask...");

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ reviews })
    });

    const data = await response.json();

    if (!response.ok) {
      renderServerStatus(false, data.error || "Analysis failed.");
      resetUi();
      return;
    }

    renderServerStatus(true, data.message || "Model is ready.");
    renderResults(data);
  } catch (error) {
    renderServerStatus(false, "Flask server is not reachable yet. Start app.py first.");
    resetUi();
  }
}

function parseUploadedText(text) {
  const rows = text
    .split(/\r?\n/)
    .map((row) => row.trim())
    .filter(Boolean);

  if (!rows.length) {
    return [];
  }

  if (rows.some((row) => row.includes(","))) {
    return rows
      .flatMap((row, index) => {
        const cells = row.split(",").map((cell) => cell.trim()).filter(Boolean);
        if (index === 0 && cells.some((cell) => /review|comment|text/i.test(cell))) {
          return [];
        }
        return cells.length > 1 ? [cells[cells.length - 1]] : cells;
      })
      .filter(Boolean);
  }

  return rows;
}

function renderResults(data) {
  document.getElementById("positive-count").textContent = data.counts.positive || 0;
  document.getElementById("neutral-count").textContent = data.counts.neutral || 0;
  document.getElementById("negative-count").textContent = data.counts.negative || 0;
  document.getElementById("total-count").textContent = data.results.length;

  preprocessPreview.className = "detail-body";
  preprocessPreview.innerHTML = data.processed_reviews.length
    ? data.processed_reviews.slice(0, 4).map((entry) => `
        <article class="preprocess-entry">
          <strong>Review ${entry.id}</strong>
          <p>${escapeHtml(entry.original)}</p>
          <p><strong>Negation:</strong> ${escapeHtml(entry.negation_text)}</p>
          <p><strong>Cleaned:</strong> ${escapeHtml(entry.cleaned_text)}</p>
        </article>
      `).join("")
    : "No preprocessing output yet.";

  resultsTableWrap.className = "results-list";
  resultsTableWrap.innerHTML = data.results.length
    ? data.results.map((entry) => `
        <article class="result-card result-card--${entry.sentiment.toLowerCase()}">
          <p class="result-line">[Review] <strong>Review:</strong> ${escapeHtml(entry.original)}</p>
          <p class="result-line prediction prediction--${entry.sentiment.toLowerCase()}">
            [${entry.sentiment}] Prediction: ${entry.sentiment} Review (${Number(entry.confidence).toFixed(2)}%)
          </p>
          <span class="score-line">Notebook model label: ${escapeHtml(entry.raw_label)}</span>
        </article>
      `).join("")
    : "No reviews analyzed yet.";

  frequencyChart.className = "detail-body";
  frequencyChart.innerHTML = data.word_frequency.length
    ? data.word_frequency.map(({ word, count }) => `
        <div class="bar-row">
          <strong>${escapeHtml(word)}</strong>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${(count / data.word_frequency[0].count) * 100}%"></div>
          </div>
          <span>${count}</span>
        </div>
      `).join("")
    : "Word frequency data will appear here.";

  renderThemeList(positiveThemes, data.positive_themes, "No data yet.");
  renderThemeList(negativeThemes, data.negative_themes, "No data yet.");

  summaryReport.className = "detail-body summary-copy";
  summaryReport.textContent = data.summary || "No summary generated.";
}

function renderThemeList(element, themes, fallback) {
  if (!themes.length) {
    element.className = "tag-list empty-state";
    element.textContent = fallback;
    return;
  }

  element.className = "tag-list";
  element.innerHTML = themes.map((theme) => `<li>${escapeHtml(theme)}</li>`).join("");
}

function renderServerStatus(ok, message) {
  serverStatus.textContent = message;
  serverStatus.className = ok ? "server-status server-status--ok" : "server-status server-status--error";
}

function resetUi() {
  document.getElementById("positive-count").textContent = "0";
  document.getElementById("neutral-count").textContent = "0";
  document.getElementById("negative-count").textContent = "0";
  document.getElementById("total-count").textContent = "0";

  preprocessPreview.className = "detail-body empty-state";
  preprocessPreview.textContent = "No preprocessing output yet.";
  resultsTableWrap.className = "results-list empty-state";
  resultsTableWrap.textContent = "No reviews analyzed yet.";
  frequencyChart.className = "detail-body empty-state";
  frequencyChart.textContent = "Word frequency data will appear here.";
  summaryReport.className = "detail-body summary-copy empty-state";
  summaryReport.textContent = "Generate a report to summarize overall customer feedback.";
  positiveThemes.className = "tag-list empty-state";
  positiveThemes.textContent = "No data yet.";
  negativeThemes.className = "tag-list empty-state";
  negativeThemes.textContent = "No data yet.";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

resetUi();
checkModelStatus();
