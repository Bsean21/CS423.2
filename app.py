from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB

try:
    import nltk
    from nltk.stem import WordNetLemmatizer
    from nltk.tokenize import word_tokenize
except Exception:
    nltk = None
    WordNetLemmatizer = None
    word_tokenize = None


BASE_DIR = Path(__file__).resolve().parent

# ✅ FIXED PATH (safe Windows format)
DATASET_PATH = Path(
    "C:/Users/ADMIN/OneDrive/Documents/Syntement Analysis/Amaya Review.csv"
)


class NotebookSentimentService:
    def __init__(self, dataset_path: Path) -> None:
        self.dataset_path = Path(dataset_path)
        self.vectorizer: TfidfVectorizer | None = None
        self.model: MultinomialNB | None = None
        self.ready = False
        self.message = ""
        self.model_accuracy: float | None = None

        self._stop_words = self._build_stop_words()
        self._lemmatizer = WordNetLemmatizer() if WordNetLemmatizer else None

        self.train()

    def _build_stop_words(self) -> set[str]:
        words = set(ENGLISH_STOP_WORDS)
        words.discard("not")
        return words

    def _tokenize(self, text: str) -> list[str]:
        if word_tokenize:
            try:
                return word_tokenize(text)
            except Exception:
                pass
        return re.findall(r"[a-zA-Z_]+", text)

    def _lemmatize(self, token: str) -> str:
        if not self._lemmatizer:
            return token
        try:
            return self._lemmatizer.lemmatize(token)
        except Exception:
            return token

    def handle_negation(self, text: str) -> str:
        text = text.lower()
        replacements = {
            "not that good": "not_good",
            "not good": "not_good",
            "not tasty": "not_tasty",
            "not delicious": "not_delicious",
            "not worth": "not_worth",
            "don't ": "not_",
            "didn't ": "not_",
            "not ": "not_",
        }
        for src, tgt in replacements.items():
            text = text.replace(src, tgt)
        return text

    def clean_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^a-zA-Z_\s]", "", text)

        tokens = self._tokenize(text)
        cleaned = []

        for word in tokens:
            if word in self._stop_words:
                continue
            cleaned.append(self._lemmatize(word))

        return " ".join(cleaned)

    @staticmethod
    def get_sentiment(score: float) -> str | None:
        if score >= 4:
            return "positive"
        if score <= 2:
            return "negative"
        return None

    def train(self) -> None:
        if not self.dataset_path.exists():
            self.ready = False
            self.message = f"Dataset not found at {self.dataset_path}"
            return

        try:
            df = pd.read_csv(self.dataset_path, encoding="latin-1")
            df = df[["Text", "Score"]].dropna()

            df["Score"] = pd.to_numeric(df["Score"], errors="coerce")
            df = df.dropna(subset=["Score"])

            df["Label"] = df["Score"].apply(self.get_sentiment)
            df = df.dropna(subset=["Label"])

            pos = df[df["Label"] == "positive"]
            neg = df[df["Label"] == "negative"]

            min_len = min(len(pos), len(neg))
            df = pd.concat([
                pos.sample(min_len, random_state=42),
                neg.sample(min_len, random_state=42),
            ]).sample(frac=1, random_state=42)

            df["Cleaned_Text"] = df["Text"].astype(str).apply(
                lambda x: self.clean_text(self.handle_negation(x))
            )

            x_train, x_test, y_train, y_test = train_test_split(
                df["Cleaned_Text"],
                df["Label"],
                test_size=0.2,
                random_state=42,
                stratify=df["Label"],
            )

            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
            x_train_vec = self.vectorizer.fit_transform(x_train)
            x_test_vec = self.vectorizer.transform(x_test)

            self.model = MultinomialNB()
            self.model.fit(x_train_vec, y_train)

            self.model_accuracy = self.model.score(x_test_vec, y_test)
            self.ready = True
            self.message = f"Model ready. Accuracy: {self.model_accuracy:.2%}"

        except Exception as e:
            self.ready = False
            self.message = f"Training failed: {e}"

    def analyze(self, reviews: list[str]) -> dict:
        if not self.ready:
            raise RuntimeError(self.message)

        cleaned = [self.clean_text(self.handle_negation(r)) for r in reviews]

        X = self.vectorizer.transform(cleaned)
        preds = self.model.predict(X)

        results = []
        counts = Counter(preds)

        for i, (text, label) in enumerate(zip(reviews, preds), start=1):
            results.append({
                "id": i,
                "text": text,
                "sentiment": label,
            })

        return {
            "message": self.message,
            "counts": dict(counts),
            "results": results,
            "accuracy": self.model_accuracy,
        }


# ================= FLASK APP =================
service = NotebookSentimentService(DATASET_PATH)
app = Flask(__name__)


@app.get("/api/model-status")
def model_status():
    return jsonify({"ready": service.ready, "message": service.message})


@app.post("/api/analyze")
def analyze():
    data = request.get_json() or {}
    reviews = data.get("reviews", [])

    reviews = [r.strip() for r in reviews if str(r).strip()]

    if not reviews:
        return jsonify({"error": "No reviews provided"}), 400

    if not service.ready:
        return jsonify({"error": service.message}), 503

    return jsonify(service.analyze(reviews))


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(BASE_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True)
