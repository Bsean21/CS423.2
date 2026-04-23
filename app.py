from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

try:
    import spacy
except Exception:  # pragma: no cover
    spacy = None

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except Exception:  # pragma: no cover
    SentimentIntensityAnalyzer = None


BASE_DIR = Path(__file__).resolve().parent
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
            "id": max((review["id"] for review in reviews), default=0) + 1,
            "review": review_text,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        reviews.append(item)
        self.save(reviews)
        return item

    def clear(self) -> None:
        self.save([])


class NotebookSentimentService:
    def __init__(self) -> None:
        self.ready = False
        self.message = ""
        self.cleaning_steps = [
            "Lowercasing",
            "Whitespace normalization",
            "Sentence segmentation",
            "Emoji preservation",
        ]
        self.nlp = None
        self.analyzer = None
        self._load_pipeline()

    def _load_pipeline(self) -> None:
        if spacy is None or SentimentIntensityAnalyzer is None:
            self.ready = False
            self.message = (
                "Missing dependencies. Install spacy and vaderSentiment, then download "
                "the en_core_web_sm model."
            )
            return

        try:
            self.nlp = spacy.load("en_core_web_sm")
            self.analyzer = SentimentIntensityAnalyzer()
            self.ready = True
            self.message = (
                "Sentence-level pipeline ready using spaCy dependency parsing and VADER sentiment."
            )
        except Exception as exc:  # pragma: no cover
            self.ready = False
            self.message = f"Pipeline setup failed: {exc}"

    def clean_text(self, text: str) -> str:
        text = str(text).lower()
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def analyze_sentence(self, sentence: str) -> dict:
        sentence_lower = sentence.lower()
        doc = self.nlp(sentence_lower)

        has_negation = any(token.dep_ == "neg" for token in doc)
        base_scores = self.analyzer.polarity_scores(sentence_lower)

        if "but" in sentence_lower:
            first, second = sentence_lower.split("but", 1)
            score1 = self.analyzer.polarity_scores(first.strip())["compound"]
            score2 = self.analyzer.polarity_scores(second.strip())["compound"]

            if score1 > 0 and score2 < 0:
                final_score = 0.0
            else:
                final_score = (0.4 * score1) + (0.6 * score2)
        else:
            final_score = base_scores["compound"]

        pos_score = base_scores["pos"]
        neg_score = base_scores["neg"]

        if abs(pos_score - neg_score) < 0.1:
            sentiment = "neutral"
        elif final_score >= 0.05:
            sentiment = "positive"
        elif final_score <= -0.05:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        confidence = round(max(base_scores["pos"], base_scores["neg"], base_scores["neu"]) * 100, 2)

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "compound": round(final_score, 4),
            "has_negation": has_negation,
            "scores": {
                "positive": round(base_scores["pos"], 4),
                "neutral": round(base_scores["neu"], 4),
                "negative": round(base_scores["neg"], 4),
            },
        }

    def process_review(self, review_text: str) -> dict:
        cleaned = self.clean_text(review_text)
        doc = self.nlp(cleaned)

        sentence_lists = []
        sentence_details = []

        for sentence_index, sent in enumerate(doc.sents, start=1):
            sentence_text = sent.text.strip()
            if not sentence_text:
                continue

            sentence_doc = self.nlp(sentence_text)
            tokens = [token.text for token in sentence_doc]
            dependencies = [
                {
                    "word": token.text,
                    "dep": token.dep_,
                    "head": token.head.text,
                }
                for token in sentence_doc
            ]
            sentiment_data = self.analyze_sentence(sentence_text)

            sentence_lists.append(tokens)
            sentence_details.append(
                {
                    "sentence_index": sentence_index,
                    "sentence": sentence_text,
                    "tokens": tokens,
                    "dependencies": dependencies,
                    **sentiment_data,
                }
            )

        final_sentiment, final_confidence = self.aggregate_review_sentiment(sentence_details)

        return {
            "cleaned_text": cleaned,
            "nested_sentence_tokens": sentence_lists,
            "sentence_details": sentence_details,
            "final_sentiment": final_sentiment,
            "final_confidence": final_confidence,
        }

    def aggregate_review_sentiment(self, sentence_details: list[dict]) -> tuple[str, float]:
        if not sentence_details:
            return "neutral", 0.0

        average_compound = sum(item["compound"] for item in sentence_details) / len(sentence_details)
        average_confidence = round(
            sum(item["confidence"] for item in sentence_details) / len(sentence_details), 2
        )
        positive_count = sum(1 for item in sentence_details if item["sentiment"] == "positive")
        negative_count = sum(1 for item in sentence_details if item["sentiment"] == "negative")

        if positive_count and negative_count and positive_count == negative_count:
            return "neutral", average_confidence
        if average_compound >= 0.05:
            return "positive", average_confidence
        if average_compound <= -0.05:
            return "negative", average_confidence
        return "neutral", average_confidence

    def analyze_reviews(self, reviews: list[dict]) -> dict:
        if not self.ready or self.nlp is None or self.analyzer is None:
            raise RuntimeError(self.message or "Pipeline is not ready.")

        processed_reviews = []
        results = []
        counts = {"positive": 0, "neutral": 0, "negative": 0}
        positive_themes = []
        negative_themes = []
        sentence_frequency = []

        for item in reviews:
            processed = self.process_review(item["review"])
            processed_reviews.append(
                {
                    "id": item["id"],
                    "original": item["review"],
                    "cleaned_text": processed["cleaned_text"],
                    "cleaning_steps": self.cleaning_steps,
                    "nested_sentence_tokens": processed["nested_sentence_tokens"],
                    "sentence_details": processed["sentence_details"],
                }
            )

            results.append(
                {
                    "id": item["id"],
                    "original": item["review"],
                    "sentiment": processed["final_sentiment"].capitalize(),
                    "confidence": processed["final_confidence"],
                }
            )
            counts[processed["final_sentiment"]] += 1

            for sentence_detail in processed["sentence_details"]:
                label = f"R{item['id']}-S{sentence_detail['sentence_index']}"
                sentence_frequency.append(
                    {"word": label, "count": len(sentence_detail["tokens"])}
                )
                if sentence_detail["sentiment"] == "positive":
                    positive_themes.append(sentence_detail["sentence"])
                if sentence_detail["sentiment"] == "negative":
                    negative_themes.append(sentence_detail["sentence"])

        total_reviews = len(results) or 1
        summary = (
            f"Objective updated: focus on sentence-level sentiment analysis with dependency parsing, "
            f"not token-level classification, and without removing emojis. Cleaning is limited to "
            f"{', '.join(self.cleaning_steps[:-1]).lower()}, while {self.cleaning_steps[-1].lower()} is preserved. "
            f"Out of {len(results)} submitted review(s), {counts['positive']} are positive, "
            f"{counts['neutral']} are neutral, and {counts['negative']} are negative."
        )

        return {
            "message": self.message,
            "counts": counts,
            "processed_reviews": processed_reviews,
            "results": results,
            "word_frequency": sentence_frequency[:8],
            "positive_themes": list(dict.fromkeys(positive_themes))[:6],
            "negative_themes": list(dict.fromkeys(negative_themes))[:6],
            "summary": summary,
        }


store = ReviewStore(STORAGE_PATH)
service = NotebookSentimentService()
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
    app.run(host="0.0.0.0", port=5000, debug=True)
