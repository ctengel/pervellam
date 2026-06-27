# pervellam

## install

1. Clone this repo and `cd` into it.
2. Install the dependencies (server + worker):

   ```
   pip install -U "yt-dlp[default]" "fastapi[standard]" \
     https://github.com/ctengel/objectindex/archive/refs/tags/v0.3.5.tar.gz \
     https://github.com/ctengel/simpler-objects/archive/refs/tags/v0.4.6.tar.gz
   ```

   `fastapi[standard]` pulls in what the server needs (FastAPI, uvicorn,
   SQLAlchemy, pydantic); `objectindex` / `simpler-objects` are used by the
   worker to upload to ObjectIndex; `yt-dlp` does the actual downloading.
3. Create your config from the template and edit it:

   ```
   cp config.samp.py config.py
   ```
4. Run the server (see below). The server listens on port **29206**.

## server

```
fastapi run --port 29206 server.py
```

or for development:

```
fastapi dev --port 29206 --host 0.0.0.0 server.py
```

## worker

A worker runs `worker.py` to pull jobs from a Pervellam server and download them
with [yt-dlp](https://github.com/yt-dlp/yt-dlp). `worker-loop.sh` wraps it in a
loop so a node keeps picking up new jobs.

### Running a worker

The worker uploads finished downloads to ObjectIndex, so it needs `OBJIDX_URL`
and `OBJIDX_AUTH` set in its environment. Point it at the server's port (29206).

One shot (picks up at most one job, then exits):

```
OBJIDX_URL=... OBJIDX_AUTH=... ./worker.py <server> <worker-id> <datadir> <bucket>
```

- `<server>` — Pervellam server URL, e.g. `http://localhost:29206/`
- `<worker-id>` — a name unique to this worker (recorded as the job's `dler`)
- `<datadir>` — temp dir for downloads; the worker creates a `<worker-id>-<job-id>`
  subdir under it per job
- `<bucket>` — ObjectIndex bucket to upload into

Keep picking up jobs in a loop (`worker-loop.sh` sleeps `<interval>` seconds
between runs):

```
OBJIDX_URL=... OBJIDX_AUTH=... ./worker-loop.sh <server> <interval> <worker-id> <datadir> <bucket>
```

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
