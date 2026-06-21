# pervellam

## server

```
fastapi run --port 29206
```

or for development:

```
fastapi dev --port 29206 --host 0.0.0.0 server.py
```

## worker

A worker runs `worker.py` to pull jobs from a Pervellam server and download them
with [yt-dlp](https://github.com/yt-dlp/yt-dlp). `worker-loop.sh` wraps it in a
loop so a node keeps picking up new jobs.

### Keeping yt-dlp up to date

yt-dlp must be kept current — sites change constantly and stable releases are often too old to work.
Install and upgrade it **including pre-releases**, as the user the worker runs as:

```
pip install --upgrade --pre yt-dlp
```

`--pre` is required: a plain `pip install --upgrade yt-dlp` only follows stable
releases and will not pick up the nightly fixes the worker needs. Re-run this command
regularly (e.g. from cron) so the node does not fall behind.

### Pointing Pervellam at it

Set `MYDLP` in `config.py` to the yt-dlp binary you just installed. A user-level
`pip install` puts the binary in `~/.local/bin`, so for a `pervellam` service user:

```
MYDLP = '/home/pervellam/.local/bin/yt-dlp'
```

See `config.samp.py` for the full config template.

## control_cli

## tw

- need app token
- need user token (can use localhost)

(see prioritize level 2)

## prioritize (autorunner)

`prioritize.py` is the autorunner: it reads an ordered priority file and starts
(and, in level 2, stops) jobs on a Pervellam `<server>` accordingly. The priority
file is plain text, one channel name per line, most important first.

```
./prioritize.py <server> <prifile> [-n]
```

There are two "intelligence levels":

### Level 1 — random spray (`-n`)

```
./prioritize.py <server> <prifile> -n
```

The easy way to get going. It looks at what's already running and adds **one
random** channel from the priority file that isn't running yet. It does **not**
check who is live, does **not** enforce `MAX`, and never stops jobs. Run it
repeatedly (e.g. on a timer) to gradually fill up.

Only needs `BASE_URL` in `config.py`.

### Level 2 — prioritized (default)

```
./prioritize.py <server> <prifile>
```

Checks the streaming site for who you follow that is **live**, then keeps the top `MAX` live
priorities running: it adds the missing ones and stops the excess.

Needs in `config.py`:

- `BASE_URL` — prefix prepended to each priority-file entry to form the job URL.
- `MAX` — max concurrent jobs to keep running.
- `TW_*` — Site API / OAuth values. You need a registered site "application"
  (client id/secret), an app access token, and a user refresh token authorized
  for the `streams/followed` scope (a localhost OAuth redirect works for the
  one-time user authorization). See `config.samp.py` for the full list and
  [OAUTH.md](OAUTH.md) for detailed instructions on how to obtain.

### Level 3 — ML (`-m`)

```
./prioritize.py <server> --ml
```

Instead of a human-written priority file, this ranks the live followed streams
with a model trained on **your own ratings** of past streams, then keeps the top
`MAX` running (same add/stop reconciliation as level 2). Use `--dry-run` to print
the ranked add/stop plan without touching the server.

This adapts the [antialgorithm](https://github.com/ctengel/antialgorithm) RSS
experiment to streams. The pipeline:

```
./stream_snap.py     # snapshot live followed streams -> ml_data/snapshots/*.json
./stream_score.py    # rate snapshots a/b/c/d/f       -> ml_data/scores.csv
./stream_train.py    # train + report accuracy        -> ml_data/model.joblib
./prioritize.py <server> --ml --dry-run   # see what it would record
```

Run `stream_snap.py` on a timer to accumulate a corpus, rate a few dozen with
`stream_score.py`, then `stream_train.py`. Re-run snap/score/train periodically
to keep the model fresh.

Extra requirements (`pip install -r requirements.txt`): `scikit-learn`, `nltk`,
`joblib`. One-time NLTK data download:

```
python -c "import nltk; nltk.download('stopwords'); nltk.download('punkt'); nltk.download('punkt_tab')"
```

Needs in `config.py`: everything from level 2 plus `ML_DATA` and `ML_MODEL`
(see `config.samp.py`).
