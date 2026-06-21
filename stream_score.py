#!/usr/bin/env python3

"""Manually rate snapshotted streams (a/b/c/d/f).

Mirrors antialgorithm's manualscore.py: present each not-yet-scored snapshot,
read a grade, append {hash, score} to ml_data/scores.csv.
"""

import csv
import json
import pathlib
import random

import config
import stream_ml


def scored_hashes(scorefile):
    """Return the set of snapshot hashes already present in scorefile."""
    if not scorefile.exists():
        return set()
    with scorefile.open(newline='') as csvfile:
        return {row['hash'] for row in csv.DictReader(csvfile)}


def score(snapdir, scorefile):
    """Interactively grade unscored snapshots, appending to scorefile."""
    done = scored_hashes(scorefile)
    paths = [p for p in snapdir.glob('*.json') if p.stem not in done]
    random.shuffle(paths)
    if not paths:
        print('Nothing left to score.')
        return
    for path in paths:
        stream = json.loads(path.read_text())
        for key, value in stream.items():
            print(key, value)
        grade = ''
        while grade not in stream_ml.GRADES:
            grade = input('a/b/c/d/f (or ctrl-c to stop): ').strip().lower()
        scorefile.parent.mkdir(parents=True, exist_ok=True)
        write_header = not scorefile.exists()
        with scorefile.open('a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['hash', 'score'])
            if write_header:
                writer.writeheader()
            writer.writerow({'hash': path.stem, 'score': grade})
        print('---')


def main():
    """Score snapshots under config.ML_DATA."""
    base = pathlib.Path(config.ML_DATA)
    score(base / 'snapshots', base / 'scores.csv')


if __name__ == '__main__':
    main()
