const reviewList = document.getElementById("review-list");
const preprocessPreview = document.getElementById("preprocess-preview");
const frequencyChart = document.getElementById("frequency-chart");
const positiveThemes = document.getElementById("positive-themes");
const negativeThemes = document.getElementById("negative-themes");
const summaryReport = document.getElementById("summary-report");

document.getElementById("refresh-btn").addEventListener("click", loadStoredReviews);
document.getElementById("analyze-btn").addEventListener("click", analyzeStoredReviews);
document.getElementById("clear-btn").addEventListener("click", clearStoredReviews);

async function checkAdminStatus() {
  return;
}

async function loadStoredReviews() {
  try {
    const response = await fetch("/api/reviews");
    const data = await response.json();
    renderStoredReviews(data.reviews || []);
  } catch (error) {
    reviewList.className = "results-list empty-state";
    reviewList.textContent = "Could not load submitted reviews.";
  }
}

async function analyzeStoredReviews() {
  try {
    const response = await fetch("/api/admin/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      }
    });
    const data = await response.json();

    if (!response.ok) {
      return;
    }

    renderAnalysis(data);
  } catch (error) {
    return;
  }
}

async function clearStoredReviews() {
  try {
    const response = await fetch("/api/reviews", { method: "DELETE" });
    const data = await response.json();
    renderStoredReviews([]);
    resetAnalysis();
  } catch (error) {
    return;
  }
}

function renderStoredReviews(reviews) {
  document.getElementById("total-count").textContent = reviews.length;
  if (!reviews.length) {
    reviewList.className = "results-list empty-state";
    reviewList.textContent = "No submitted reviews yet.";
    return;
  }

  reviewList.className = "results-list";
  reviewList.innerHTML = reviews.map((item) => `
    <article class="result-card">
      <p class="result-line"><strong>#${item.id}</strong> Submitted review</p>
      <p class="result-line">${escapeHtml(item.review)}</p>
      <span class="score-line">Created: ${escapeHtml(item.created_at)}</span>
    </article>
  `).join("");
}

function renderAnalysis(data) {
  document.getElementById("positive-count").textContent = data.counts.positive || 0;
  document.getElementById("neutral-count").textContent = data.counts.neutral || 0;
  document.getElementById("negative-count").textContent = data.counts.negative || 0;
  document.getElementById("total-count").textContent = data.results.length || 0;

  reviewList.className = "results-list";
  reviewList.innerHTML = data.results.length ? data.results.map((entry) => `
    <article class="result-card result-card--${entry.sentiment.toLowerCase()}">
      <p class="result-line">[Review] <strong>Review:</strong> ${escapeHtml(entry.original)}</p>
      <p class="result-line prediction prediction--${entry.sentiment.toLowerCase()}">
        [${entry.sentiment}] Prediction: ${entry.sentiment} Review (${Number(entry.confidence).toFixed(2)}%)
      </p>
      <span class="score-line">Stored review id: ${entry.id}</span>
    </article>
  `).join("") : "No submitted reviews yet.";

  preprocessPreview.className = "detail-body";
  preprocessPreview.innerHTML = data.processed_reviews.length ? data.processed_reviews.map((entry) => `
    <article class="preprocess-entry">
      <strong>Review ${entry.id}</strong>
      <p>${escapeHtml(entry.original)}</p>
      <p><strong>Cleaning:</strong> ${entry.cleaning_steps.map(escapeHtml).join(", ")}</p>
      <p><strong>Cleaned:</strong> ${escapeHtml(entry.cleaned_text)}</p>
      <p><strong>Nested sentence tokens:</strong> ${entry.nested_sentence_tokens.map((tokens) => `[${tokens.map(escapeHtml).join(", ")}]`).join(" ")}</p>
      ${entry.sentence_details.map((detail) => `
        <div class="preprocess-entry">
          <p><strong>Sentence ${detail.sentence_index}:</strong> ${escapeHtml(detail.sentence)}</p>
          <p><strong>Tokens:</strong> ${detail.tokens.map(escapeHtml).join(", ")}</p>
          <p><strong>Dependencies:</strong> ${detail.dependencies.map((dep) => `${escapeHtml(dep.word)}(${escapeHtml(dep.dep)} -> ${escapeHtml(dep.head)})`).join(", ")}</p>
          <p><strong>Sentence sentiment:</strong> ${escapeHtml(detail.sentiment)} (${Number(detail.confidence).toFixed(2)}%)</p>
        </div>
      `).join("")}
    </article>
  `).join("") : "Analysis output will appear here.";

  frequencyChart.className = "detail-body";
  frequencyChart.innerHTML = data.word_frequency.length ? data.word_frequency.map(({ word, count }) => `
    <div class="bar-row">
      <strong>${escapeHtml(word)}</strong>
      <div class="bar-track">
        <div class="bar-fill" style="width: ${(count / data.word_frequency[0].count) * 100}%"></div>
      </div>
      <span>${count}</span>
    </div>
  `).join("") : "Word frequency data will appear here.";

  renderThemeList(positiveThemes, data.positive_themes, "No data yet.");
  renderThemeList(negativeThemes, data.negative_themes, "No data yet.");
  summaryReport.className = "detail-body summary-copy";
  summaryReport.textContent = data.summary || "Run analysis to generate a report.";
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

function resetAnalysis() {
  document.getElementById("positive-count").textContent = "0";
  document.getElementById("neutral-count").textContent = "0";
  document.getElementById("negative-count").textContent = "0";
  document.getElementById("total-count").textContent = "0";
  preprocessPreview.className = "detail-body empty-state";
  preprocessPreview.textContent = "Analysis output will appear here.";
  frequencyChart.className = "detail-body empty-state";
  frequencyChart.textContent = "Word frequency data will appear here.";
  positiveThemes.className = "tag-list empty-state";
  positiveThemes.textContent = "No data yet.";
  negativeThemes.className = "tag-list empty-state";
  negativeThemes.textContent = "No data yet.";
  summaryReport.className = "detail-body summary-copy empty-state";
  summaryReport.textContent = "Run analysis to generate a report.";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

checkAdminStatus();
loadStoredReviews();
resetAnalysis();
