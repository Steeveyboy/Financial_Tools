# Sentiment Analysis

A Flask web application that scrapes news articles from multiple sources and runs sentiment analysis using a trained NLP pipeline.

## Features

- Search for any keyword to find relevant news articles
- Aggregates articles from Reuters and CBC
- Runs sentiment analysis on each article using a pre-trained scikit-learn model
- Displays an overall sentiment score with a visual progress bar

## Tech Stack

- **Backend:** Python, Flask
- **NLP:** NLTK, scikit-learn (pickled pipeline)
- **Web Scraping:** Requests, requests-html
- **Frontend:** HTML, Tailwind CSS, DaisyUI

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Download NLTK stopwords (first time only):
   ```python
   import nltk
   nltk.download('stopwords')
   ```

3. Run the app:
   ```bash
   python app.py
   ```

4. Open your browser to `http://localhost:5151`

## How It Works

1. User enters a keyword in the search bar
2. The app scrapes recent articles from Reuters and CBC matching that keyword
3. Each article's description is preprocessed (lowercased, stopwords removed, punctuation stripped)
4. A pre-trained sentiment model predicts a sentiment score (0–1) for each article
5. Results are displayed as cards with individual scores and an overall sentiment bar
