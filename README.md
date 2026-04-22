# Customer and Admin Review Flow

This version separates the app into two interfaces:

- `index.html` for customers to submit a review only
- `admin.html` for admins to view stored reviews and analyze them

## Routes

- `/` customer review form
- `/admin` admin dashboard

## Dataset

The app is now configured for:

`C:\Users\ADMIN\OneDrive\Documents\Syntement Analysis\Amaya Review.csv`

You can still override that path with `REVIEWS_CSV`.

## Dataset columns used

- `review`
- `sentiment`

Sentiment labels are normalized as:

- `-1` -> `negative`
- `0` -> `neutral`
- `1` -> `positive`

## Note

Your OneDrive `app.py` still expects `Text` and `Score`, which does not match this dataset. The workspace version has been updated to use the real CSV structure.
