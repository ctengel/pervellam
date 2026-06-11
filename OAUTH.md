# Twitch API setup

This is the detailed setup for `prioritize.py` **level 2** (prioritized) mode, which
uses the Twitch Helix API to find which of your followed channels are currently live.
Level 1 (random spray, `-n`) does **not** need any of this — see the README.

The values you collect here go into your `config.py` (see `config.samp.py` for the
`TW_*` placeholders). At the end you'll have all of:

| config var | what it is |
| ---------- | ---------- |
| `TW_URL`   | Helix API base, `https://api.twitch.tv/helix/` |
| `TW_IDU`   | OAuth token endpoint, `https://id.twitch.tv/oauth2/token` |
| `TW_CLI`   | application **Client ID** |
| `TW_CLS`   | application **Client Secret** |
| `TW_APT`   | app access token (client-credentials grant) |
| `TW_URT`   | user **refresh** token (authorization-code grant) |
| `TW_USR`   | your Twitch login name |
| `TW_UST`   | *optional* — user access token; normally derived from `TW_URT` at runtime |

`TW_URL` and `TW_IDU` are the same for everyone; the rest are specific to your app and
account.

## 1. Register a Twitch application

1. Go to the [Twitch developer console](https://dev.twitch.tv/console/apps) and
   **Register Your Application**.
2. Set an OAuth **Redirect URL**. A localhost URL such as `http://localhost:3000` is
   fine — it only needs to receive the one-time authorization code in step 3; nothing
   has to actually be listening there (you can read the code straight out of the
   browser address bar).
3. Note the **Client ID** → `TW_CLI`.
4. Create a **Client Secret** → `TW_CLS`. Treat it like a password.

## 2. Get an app access token (`TW_APT`)

The app token uses the **client-credentials** grant — no user involved:

```
curl -X POST https://id.twitch.tv/oauth2/token \
  -d client_id=$TW_CLI \
  -d client_secret=$TW_CLS \
  -d grant_type=client_credentials
```

The response JSON's `access_token` → `TW_APT`.

App tokens expire (a few weeks). `tw.py` does **not** auto-refresh `TW_APT`, so if app
calls start returning 401 you'll need to re-run this command and update `config.py`.

## 3. Get a user refresh token (`TW_URT`)

`prioritize.py` reads *your* followed-live list, so it needs a **user** token authorized
with the `user:read:follows` scope. We obtain a long-lived **refresh** token once via the
**authorization-code** grant; `tw.py` exchanges it for a short-lived access token on every
run, so you never have to repeat this.

**a. Authorize in a browser.** Open this URL (filling in your client id and the same
redirect URL you registered):

```
https://id.twitch.tv/oauth2/authorize?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost:3000&scope=user%3Aread%3Afollows
```

Approve the prompt. Twitch redirects you to
`http://localhost:3000/?code=AUTHCODE&scope=...`. Copy the `AUTHCODE` from the address
bar (the page itself failing to load is expected).

**b. Exchange the code for tokens:**

```
curl -X POST https://id.twitch.tv/oauth2/token \
  -d client_id=$TW_CLI \
  -d client_secret=$TW_CLS \
  -d code=AUTHCODE \
  -d grant_type=authorization_code \
  -d redirect_uri=http://localhost:3000
```

The response JSON's `refresh_token` → `TW_URT`. (The `access_token` in the same response
is the short-lived user token; you can ignore it — `tw.py` regenerates it from the refresh
token. If you ever want to pin one manually it maps to the optional `TW_UST`.)

Authorization codes are single-use and expire fast — if the exchange fails, redo step (a).

## 4. Set your login (`TW_USR`)

`TW_USR` is your Twitch login name (the one in your channel URL, lowercase). `tw.py` uses
it to look up your numeric user id via Helix `users`, which is then passed to
`streams/followed`.

## 5. Verify

With `config.py` filled in, a quick check from the repo root:

```
python3 -c "
import config, tw
t = tw.Tw(url=config.TW_URL, client_id=config.TW_CLI,
          app_access_token=config.TW_APT, user_refresh_token=config.TW_URT,
          login=config.TW_USR, id_url=config.TW_IDU, client_secret=config.TW_CLS)
print('user id:', t.get_user_id())
print('live followed:', [s['user_login'] for s in t.followed()])
"
```

If that prints your numeric user id and a (possibly empty) list of live channels, level 2
is ready:

```
./prioritize.py <server> <prifile>
```

### Troubleshooting

- **401 on `users` / app calls** — `TW_APT` expired; redo step 2.
- **401 on `streams/followed`** — refresh-token exchange failed or scope missing; redo
  step 3 making sure `scope=user:read:follows` is present.
- **`IndexError` from `get_user_id`** — `TW_USR` doesn't match an existing login.
