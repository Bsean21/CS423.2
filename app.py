from __future__ import annotations

import csv
import json
from io import StringIO
import pickle
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, Response

try:
    import spacy
except Exception:  # pragma: no cover
    spacy = None

try:
    import joblib
except Exception:  # pragma: no cover
    joblib = None

BASE_DIR = Path(__file__).resolve().parent
STORAGE_PATH = BASE_DIR / "reviews_store.json"
VECTORIZER_PATH = Path("C:/Users/ADMIN/Downloads/tfidf_vectorizer.pkl")
MODEL_PATH = Path("C:/Users/ADMIN/Downloads/sentiment_model.pkl")


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
        self.vectorizer = None
        self.model = None
        self._load_pipeline()

    def _load_pipeline(self) -> None:
        if spacy is None:
            self.ready = False
            self.message = (
                "Missing dependencies. Install spacy and download the en_core_web_sm model."
            )
            return

        if not VECTORIZER_PATH.exists() or not MODEL_PATH.exists():
            self.ready = False
            self.message = "Missing tfidf_vectorizer.pkl or sentiment_model.pkl in Downloads."
            return

        try:
            self.nlp = spacy.load("en_core_web_sm")
            self.vectorizer = self._load_serialized_object(VECTORIZER_PATH)
            self.model = self._load_serialized_object(MODEL_PATH)
            self.ready = True
            self.message = (
                "Sentence-level pipeline ready using spaCy parsing with the saved TF-IDF vectorizer and sentiment model."
            )
        except Exception as exc:  # pragma: no cover
            self.ready = False
            self.message = f"Pipeline setup failed: {exc}"

    def _load_serialized_object(self, path: Path):
        pickle_error = None

        try:
            with path.open("rb") as file_obj:
                return pickle.load(file_obj)
        except Exception as exc:  # pragma: no cover
            pickle_error = exc

        if joblib is not None:
            try:
                return joblib.load(path)
            except Exception as joblib_exc:  # pragma: no cover
                raise RuntimeError(
                    f"Could not load {path.name}. pickle error: {pickle_error}; joblib error: {joblib_exc}"
                ) from joblib_exc

        raise RuntimeError(
            f"Could not load {path.name}. pickle error: {pickle_error}. "
            "Install joblib to try an alternate loader."
        )

    def clean_text(self, text: str) -> str:
        text = str(text).lower()
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def normalize_model_label(value) -> str:
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
            "neg": "negative",
            "neu": "neutral",
            "pos": "positive",
        }
        return mapping.get(value, str(value).lower())

    def analyze_sentence(self, sentence: str) -> dict:
        sentence_lower = sentence.lower()
        doc = self.nlp(sentence_lower)

        has_negation = any(token.dep_ == "neg" for token in doc)
        cleaned_sentence = self.clean_text(sentence_lower)
        vectorized_sentence = self.vectorizer.transform([cleaned_sentence])
        raw_prediction = self.model.predict(vectorized_sentence)[0]
        sentiment = self.normalize_model_label(raw_prediction)

        confidence = 0.0
        scores = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
        if hasattr(self.model, "predict_proba"):
            probabilities = self.model.predict_proba(vectorized_sentence)[0]
            classes = [self.normalize_model_label(label) for label in self.model.classes_]
            for label, probability in zip(classes, probabilities):
                if label in scores:
                    scores[label] = round(float(probability), 4)
            confidence = round(max(probabilities) * 100, 2)
        else:
            confidence = 100.0

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "compound": round(scores["positive"] - scores["negative"], 4),
            "has_negation": has_negation,
            "scores": scores,
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
        if not self.ready or self.nlp is None or self.vectorizer is None or self.model is None:
            raise RuntimeError(self.message or "Pipeline is not ready.")

        processed_reviews = []
        results = []
        counts = {"positive": 0, "neutral": 0, "negative": 0}
        positive_themes = []
        neutral_themes = []
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
                if sentence_detail["sentiment"] == "neutral":
                    neutral_themes.append(sentence_detail["sentence"])
                if sentence_detail["sentiment"] == "negative":
                    negative_themes.append(sentence_detail["sentence"])

        total_reviews = len(results) or 1
        summary = (
            f"Web system updated to use the saved TF-IDF vectorizer and sentiment model. "
            f"Sentence segmentation and dependency parsing are still shown in the admin dashboard, while cleaning is limited to "
            f"{', '.join(self.cleaning_steps[:-1]).lower()} and {self.cleaning_steps[-1].lower()}. "
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
            "neutral_themes": list(dict.fromkeys(neutral_themes))[:6],
            "negative_themes": list(dict.fromkeys(negative_themes))[:6],
            "summary": summary,
        }


def export_reviews_csv(analysis: dict) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "review_id",
            "review_text",
            "final_sentiment",
            "final_confidence",
            "sentence_index",
            "sentence_text",
            "sentence_sentiment",
            "sentence_confidence",
            "tokens",
            "dependencies",
        ]
    )

    processed_map = {item["id"]: item for item in analysis["processed_reviews"]}
    result_map = {item["id"]: item for item in analysis["results"]}

    for review_id, processed in processed_map.items():
        result = result_map.get(review_id, {})
        for sentence_detail in processed["sentence_details"]:
            dependencies = "; ".join(
                f"{dep['word']}({dep['dep']} -> {dep['head']})"
                for dep in sentence_detail["dependencies"]
            )
            writer.writerow(
                [
                    review_id,
                    processed["original"],
                    result.get("sentiment", ""),
                    result.get("confidence", ""),
                    sentence_detail["sentence_index"],
                    sentence_detail["sentence"],
                    sentence_detail["sentiment"],
                    sentence_detail["confidence"],
                    " | ".join(sentence_detail["tokens"]),
                    dependencies,
                ]
            )

    return buffer.getvalue()


def export_summary_csv(analysis: dict) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "value"])
    writer.writerow(["positive_reviews", analysis["counts"]["positive"]])
    writer.writerow(["neutral_reviews", analysis["counts"]["neutral"]])
    writer.writerow(["negative_reviews", analysis["counts"]["negative"]])
    writer.writerow(["summary", analysis["summary"]])
    writer.writerow(["positive_themes", " | ".join(analysis["positive_themes"])])
    writer.writerow(["neutral_themes", " | ".join(analysis["neutral_themes"])])
    writer.writerow(["negative_themes", " | ".join(analysis["negative_themes"])])
    return buffer.getvalue()


def export_combined_csv(analysis: dict) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["SUMMARY"])
    writer.writerow(["metric", "value"])
    writer.writerow(["positive_reviews", analysis["counts"]["positive"]])
    writer.writerow(["neutral_reviews", analysis["counts"]["neutral"]])
    writer.writerow(["negative_reviews", analysis["counts"]["negative"]])
    writer.writerow(["summary", analysis["summary"]])
    writer.writerow(["positive_themes", " | ".join(analysis["positive_themes"])])
    writer.writerow(["neutral_themes", " | ".join(analysis["neutral_themes"])])
    writer.writerow(["negative_themes", " | ".join(analysis["negative_themes"])])
    writer.writerow([])
    writer.writerow(["REVIEW_DETAILS"])
    writer.writerow(
        [
            "review_id",
            "review_text",
            "final_sentiment",
            "final_confidence",
            "sentence_index",
            "sentence_text",
            "sentence_sentiment",
            "sentence_confidence",
            "tokens",
            "dependencies",
        ]
    )

    processed_map = {item["id"]: item for item in analysis["processed_reviews"]}
    result_map = {item["id"]: item for item in analysis["results"]}

    for review_id, processed in processed_map.items():
        result = result_map.get(review_id, {})
        for sentence_detail in processed["sentence_details"]:
            dependencies = "; ".join(
                f"{dep['word']}({dep['dep']} -> {dep['head']})"
                for dep in sentence_detail["dependencies"]
            )
            writer.writerow(
                [
                    review_id,
                    processed["original"],
                    result.get("sentiment", ""),
                    result.get("confidence", ""),
                    sentence_detail["sentence_index"],
                    sentence_detail["sentence"],
                    sentence_detail["sentiment"],
                    sentence_detail["confidence"],
                    " | ".join(sentence_detail["tokens"]),
                    dependencies,
                ]
            )

    return buffer.getvalue()


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


@app.get("/api/admin/export/all.csv")
def download_all_csv():
    reviews = store.load()
    if not reviews:
        return jsonify({"error": "No submitted reviews available for export."}), 400
    if not service.ready:
        return jsonify({"error": service.message}), 503
    analysis = service.analyze_reviews(reviews)
    csv_content = export_combined_csv(analysis)
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=admin_review_export.csv"},
    )


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
