#!/usr/bin/env python3

"""Train the stream-rating model and report accuracy.

Mirrors antialgorithm's rssfeaturize.run_it(): load scored snapshots, do a
train/test split for a quick accuracy read-out, then retrain on everything and
save the model for prioritize.py to use.
"""

import csv
import json
import pathlib

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

import config
import stream_ml


def load_scored(snapdir, scorefile):
    """Return [{'hash', 'score', 'data'}] for every scored snapshot."""
    with scorefile.open(newline='') as csvfile:
        rows = list(csv.DictReader(csvfile))
    for row in rows:
        row['data'] = json.loads((snapdir / (row['hash'] + '.json')).read_text())
    return rows


def report(scored):
    """Hold-out split, train, and print accuracy + classification report."""
    train_rows, test_rows = train_test_split(scored, test_size=0.2,
                                             random_state=42)
    vectorizer, model = stream_ml.train(train_rows)
    features = vectorizer.transform(stream_ml.featurize(r['data'])
                                    for r in test_rows)
    predicted = model.predict(features)
    actual = [r['score'] for r in test_rows]
    print('Accuracy:', accuracy_score(actual, predicted))
    print('Classification Report:\n', classification_report(actual, predicted,
                                                            zero_division=0))


def main():
    """Evaluate, then train on all data and save to config.ML_MODEL."""
    base = pathlib.Path(config.ML_DATA)
    scored = load_scored(base / 'snapshots', base / 'scores.csv')
    if not scored:
        print('No scored snapshots; run stream_score.py first.')
        return
    report(scored)
    vectorizer, model = stream_ml.train(scored)
    pathlib.Path(config.ML_MODEL).parent.mkdir(parents=True, exist_ok=True)
    stream_ml.save_model(config.ML_MODEL, vectorizer, model)
    print('Saved model to', config.ML_MODEL)


if __name__ == '__main__':
    main()
