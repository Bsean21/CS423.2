from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB

try:
    from nltk.stem import WordNetLemmatizer
    from nltk.tokenize import word_tokenize
except Exception:  # pragma: no cover
    WordNetLemmatizer = None
    word_tokenize = None


BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = Path(
    os.getenv(
        "REVIEWS_CSV",
        "C:/Users/ADMIN/OneDrive/Documents/Syntement Analysis/Amaya Review.csv",
    )
)
STORAGE_PATH = BASE_DIR / "reviews_store.json"


class ReviewStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not self.path.exists():
            self.save([])

    def load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save(self, reviews: list[dict]) -> None:
        self.path.write_text(json.dumps(reviews, indent=2), encoding="utf-8")

    def add_review(self, review_text: str) -> dict:
        reviews = self.load()
        item = {
            "id": (max((review["id"] for review in reviews), default=0) + 1),
            "review": review_text,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        reviews.append(item)
        self.save(reviews)
        return item

    def clear(self) -> None:
        self.save([])


class NotebookSentimentService:
    def __init__(self, dataset_path: Path) -> None:
        self.dataset_path = dataset_path
        self.vectorizer: TfidfVectorizer | None = None
        self.model: MultinomialNB | None = None
        self.ready = False
        self.message = ""
        self.model_accuracy: float | None = None
        self._stop_words = set(ENGLISH_STOP_WORDS)
        self._stop_words.discard("not")
        self._lemmatizer = WordNetLemmatizer() if WordNetLemmatizer else None
        self.train()

    def _tokenize(self, text: str) -> list[str]:
        if word_tokenize:
            try:
                return word_tokenize(text)
            except LookupError:
                pass
        return re.findall(r"[a-zA-Z_]+", text)

    def _lemmatize(self, token: str) -> str:
        if not self._lemmatizer:
            return token
        try:
            return self._lemmatizer.lemmatize(token)
        except LookupError:
            return token

    def handle_negation(self, text: str) -> str:
        text = text.lower()
        replacements = {
            "not that good": "not_good",
            "not that tasty": "not_tasty",
            "not that delicious": "not_delicious",
            "not good": "not_good",
            "not tasty": "not_tasty",
            "not delicious": "not_delicious",
            "not worth": "not_worth",
            "don't ": "not_",
            "didn't ": "not_",
            "not ": "not_",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def clean_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^a-zA-Z_\s]", "", text)
        tokens = self._tokenize(text)
        cleaned = []
        for token in tokens:
            if token in self._stop_words:
                continue
            cleaned.append(self._lemmatize(token))
        return " ".join(cleaned)

    @staticmethod
    def normalize_sentiment(value) -> str | None:
        mapping = {
            -1: "negative",
            0: "neutral",
            1: "positive",
            "-1": "negative",
            "0": "neutral",
            "1": "positive",
            "negative": "negative",
            "neutral": "neutral",
            "positive": "positive",
        }
        return mapping.get(value)

    def train(self) -> None:
        if not self.dataset_path.exists():
            self.ready = False
            self.message = (
                f"Dataset not found. Put Amaya Review.csv at {self.dataset_path} "
                "or set the REVIEWS_CSV environment variable."
            )
            return

        try:
            df = pd.read_csv(self.dataset_path, encoding="latin-1")
            df = df[["review", "sentiment"]].copy().dropna()
            df["Label"] = df["sentiment"].apply(self.normalize_sentiment)
            df = df.dropna(subset=["Label"])

            # Keeps the three real dataset classes instead of forcing score-based binary labels.
            df["Negation_Text"] = df["review"].astype(str).apply(self.handle_negation)
            df["Cleaned_Text"] = df["Negation_Text"].apply(self.clean_text)

            x_train, x_test, y_train, y_test = train_test_split(
                df["Cleaned_Text"],
                df["Label"],
                test_size=0.2,
                random_state=42,
                stratify=df["Label"],
            )

            stop_words = list(ENGLISH_STOP_WORDS)
            if "not" in stop_words:
                stop_words.remove("not")

            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words=stop_words)
            x_train_vec = self.vectorizer.fit_transform(x_train)
            x_test_vec = self.vectorizer.transform(x_test)

            self.model = MultinomialNB()
            self.model.fit(x_train_vec, y_train)
            self.model_accuracy = float(self.model.score(x_test_vec, y_test))
            self.ready = True
            self.message = (
                "Model ready using Amaya Review.csv. "
                f"Validation accuracy: {self.model_accuracy * 100:.2f}%."
            )
        except Exception as exc:  # pragma: no cover
            self.ready = False
            self.message = f"Training failed: {exc}"

    def analyze_reviews(self, reviews: list[dict]) -> dict:
        if not self.ready or not self.vectorizer or not self.model:
            raise RuntimeError(self.message or "Model is not ready.")

        processed_reviews = []
        cleaned_texts = []

        for item in reviews:
            negation_text = self.handle_negation(item["review"])
            cleaned_text = self.clean_text(negation_text)
            cleaned_texts.append(cleaned_text)
            processed_reviews.append(
                {
                    "id": item["id"],
                    "original": item["review"],
                    "negation_text": negation_text,
                    "cleaned_text": cleaned_text,
                }
            )

        vectors = self.vectorizer.transform(cleaned_texts)
        labels = self.model.predict(vectors)
        probabilities = self.model.predict_proba(vectors)

        results = []
        counts = {"positive": 0, "neutral": 0, "negative": 0}
        positive_tokens: list[str] = []
        negative_tokens: list[str] = []
        token_counter: Counter[str] = Counter()
        positive_index = list(self.model.classes_).index("positive")

        for processed, raw_label, probs in zip(processed_reviews, labels, probabilities):
            positive_percent = round(float(probs[positive_index]) * 100, 2)

            if positive_percent < 50:
                derived_label = "negative"
            elif positive_percent == 50:
                derived_label = "neutral"
            else:
                derived_label = "positive"

            sentiment = derived_label.capitalize()
            results.append(
                {
                    "id": processed["id"],
                    "original": processed["original"],
                    "raw_label": raw_label,
                    "sentiment": sentiment,
                    "confidence": positive_percent,
                }
            )
            counts[derived_label] += 1
            tokens = [token for token in processed["cleaned_text"].split() if token]
            token_counter.update(tokens)
            if derived_label == "positive":
                positive_tokens.extend(tokens)
            if derived_label == "negative":
                negative_tokens.extend(tokens)

        word_frequency = [{"word": word, "count": count} for word, count in token_counter.most_common(8)]
        positive_themes = [word for word, _ in Counter(positive_tokens).most_common(6)]
        negative_themes = [word for word, _ in Counter(negative_tokens).most_common(6)]
        total = len(results) or 1
        summary = (
            f"Out of {len(results)} submitted review(s), {counts['positive']} were predicted as positive, "
            f"{counts['neutral']} as neutral, and {counts['negative']} as negative. Positive reviews account for "
            f"{(counts['positive'] / total) * 100:.1f}% of the current submissions, neutral reviews account for "
            f"{(counts['neutral'] / total) * 100:.1f}%, and negative reviews account for "
            f"{(counts['negative'] / total) * 100:.1f}%. Recurring positive terms include "
            f"{', '.join(positive_themes[:3]) or 'none'}, while recurring negative terms include "
            f"{', '.join(negative_themes[:3]) or 'none'}."
        )

        return {
            "message": self.message,
            "counts": counts,
            "processed_reviews": processed_reviews,
            "results": results,
            "word_frequency": word_frequency,
            "positive_themes": positive_themes,
            "negative_themes": negative_themes,
            "summary": summary,
        }


store = ReviewStore(STORAGE_PATH)
service = NotebookSentimentService(DATASET_PATH)
app = Flask(__name__)


@app.get("/api/model-status")
def model_status():
    return jsonify({"ready": service.ready, "message": service.message})


@app.get("/api/reviews")
def get_reviews():
    return jsonify({"reviews": store.load()})


@app.post("/api/reviews")
def create_review():
    payload = request.get_json(silent=True) or {}
    review = str(payload.get("review", "")).strip()
    if not review:
        return jsonify({"error": "Please provide a review."}), 400
    item = store.add_review(review)
    return jsonify({"message": "Review submitted successfully.", "review": item}), 201


@app.delete("/api/reviews")
def delete_reviews():
    store.clear()
    return jsonify({"message": "Stored reviews cleared."})


@app.post("/api/admin/analyze")
def analyze_reviews():
    reviews = store.load()
    if not reviews:
        return jsonify({"error": "No submitted reviews available for analysis."}), 400
    if not service.ready:
        return jsonify({"error": service.message}), 503
    return jsonify(service.analyze_reviews(reviews))


@app.get("/")
def customer_page():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/admin")
def admin_page():
    return send_from_directory(BASE_DIR, "admin.html")


@app.get("/<path:filename>")
def assets(filename: str):
    return send_from_directory(BASE_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True)

