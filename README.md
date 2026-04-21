# Flask Sentiment App

This app connects the UI to a Flask backend based on the notebook pipeline from `FINAL_ACT3_AMAZON-FOOD-REVIEW (1).ipynb`.

## Expected dataset

Place `Reviews.csv` in this folder:

`C:\Users\ADMIN\Documents\Codex\2026-04-21-files-mentioned-by-the-user-the-2`

Or set an environment variable before running:

`REVIEWS_CSV=C:\path\to\Reviews.csv`

## Run

1. Install dependencies from `requirements.txt`.
2. Start Flask with `python app.py`.
3. Open `http://127.0.0.1:5000`.

## Notebook flow mirrored in the backend

- Uses `Text` and `Score`
- Maps scores `>= 4` to `positive`
- Maps scores `<= 2` to `negative`
- Drops neutral reviews
- Balances positive and negative classes
- Applies negation handling and text cleaning
- Uses `TfidfVectorizer(ngram_range=(1, 2))`
- Trains `MultinomialNB`
