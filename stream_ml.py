"""Shared ML core for guessing stream ratings.

Mirrors the antialgorithm RSS experiment (rssfeaturize.py) but adapted to Twitch
stream dicts and made reusable: train_save once, then load+rank live streams from
prioritize.py. Featurization lives here so training and prediction always agree.
"""

import re
import joblib
import numpy as np
import nltk
import sklearn.svm
from sklearn.feature_extraction.text import TfidfVectorizer

STOPWORDS = set(nltk.corpus.stopwords.words('english'))

# Letter grades as a scale, for ranking model predictions (a best, f worst).
GRADES = {'a': 4, 'b': 3, 'c': 2, 'd': 1, 'f': 0}


def tokenize(text):
    """Lowercase, strip non-letters, drop stopwords (same as the RSS experiment)."""
    if not text:
        return ''
    cleaned = re.sub(r'[^a-z\s]', '', text.lower())
    return ' '.join(word for word in nltk.tokenize.word_tokenize(cleaned)
                    if word not in STOPWORDS)


def featurize(stream):
    """Turn a Twitch stream dict into a token blob for TF-IDF.

    Combines the free-text title with the (already categorical) game, channel and
    language so a single text vectorizer can learn from all of them.
    """
    parts = [tokenize(stream.get('title', ''))]
    for key in ('game_name', 'user_login', 'language'):
        value = stream.get(key)
        if value:
            parts.append(str(value).lower())
    return ' '.join(part for part in parts if part)


def train(scored):
    """Fit a vectorizer + linear SVM from [{'score', 'data'}] rows.

    Returns (vectorizer, model). A plain SVC is used; rank_score() turns its
    decision_function into a smooth expected-grade value, so no (fragile on small
    or imbalanced corpora) probability calibration is needed.
    """
    labels = [row['score'] for row in scored]
    vectorizer = TfidfVectorizer(max_features=262144)
    features = vectorizer.fit_transform(featurize(row['data']) for row in scored)
    model = sklearn.svm.SVC(kernel='linear')
    model.fit(features, labels)
    return vectorizer, model


def save_model(path, vectorizer, model):
    """Persist the fitted vectorizer and model together."""
    joblib.dump({'vectorizer': vectorizer, 'model': model}, path)


def load_model(path):
    """Load a (vectorizer, model) pair saved by save_model()."""
    bundle = joblib.load(path)
    return bundle['vectorizer'], bundle['model']


def rank_score(vectorizer, model, stream):
    """Expected grade value for a stream, for top-MAX ranking (higher = better).

    Softmaxes the SVM's per-class decision scores into pseudo-probabilities and
    weights them by the numeric grade scale, so two streams predicted the same
    letter still order sensibly.
    """
    features = vectorizer.transform([featurize(stream)])
    scores = np.atleast_1d(model.decision_function(features)[0]).astype(float)
    if len(model.classes_) == 2 and scores.shape == (1,):
        # Binary SVC returns a single signed score for the second class.
        scores = np.array([-scores[0], scores[0]])
    weights = np.exp(scores - scores.max())
    weights /= weights.sum()
    return sum(weight * GRADES.get(label, 0)
               for label, weight in zip(model.classes_, weights))
