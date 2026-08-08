#!/usr/bin/env python3

"""Snapshot available (followed, live) streams as hashed JSON files.

Mirrors antialgorithm's rssparse.py: pull the current pool of streams from the
site API and dump each as ml_data/snapshots/<hash>.json. Idempotent, so run it
on a timer to accumulate a corpus to rate and train on.
"""

import json
import hashlib
import pathlib

import tw
import config


def snap(two, snapdir):
    """Write any not-yet-seen live streams to snapdir; return count written."""
    snapdir.mkdir(parents=True, exist_ok=True)
    written = 0
    for stream in two.followed():
        outvers = json.dumps(stream, sort_keys=True)
        outhash = hashlib.sha256(outvers.encode('utf-8')).hexdigest()
        filename = snapdir / (outhash + '.json')
        if not filename.exists():
            filename.write_text(outvers)
            written += 1
    return written


def main():
    """Snapshot using config TW_* values into config.ML_DATA/snapshots."""
    two = tw.Tw.from_config(config)
    snapdir = pathlib.Path(config.ML_DATA) / 'snapshots'
    written = snap(two, snapdir)
    print(f'Wrote {written} new snapshot(s) to {snapdir}')


if __name__ == '__main__':
    main()
