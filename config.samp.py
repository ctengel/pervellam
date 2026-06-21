# Path to the yt-dlp binary the worker runs. Keep yt-dlp fully up to date with
# `pip install --upgrade --pre yt-dlp`; a user-level install lands in ~/.local/bin,
# e.g. MYDLP = '/home/pervellam/.local/bin/yt-dlp'
MYDLP = '/usr/bin/yt-dlp'
BASE_URL = 'https://www.website.com/'

# prioritize.py level 2 (prioritized) and level 3 (ML) only
MAX = 5  # max concurrent jobs to keep running

# prioritize.py level 3 (ML) and the stream_* tooling
ML_DATA = './ml_data'                    # snapshots/ and scores.csv live here
ML_MODEL = './ml_data/model.joblib'      # trained model saved/loaded here

# OAuth (prioritize.py level 2 only)
TW_URL = 'https://api.website.com/helix/'   # Helix API base
TW_IDU = 'https://id.website.com/oauth2/token'  # OAuth token endpoint
TW_CLI = 'your-app-client-id'
TW_CLS = 'your-app-client-secret'
TW_APT = 'your-app-access-token'
TW_URT = 'your-user-refresh-token'  # obtained via a localhost OAuth redirect
TW_USR = 'your-user-login'        # login name whose followed live streams we read
#TW_UST = 'your-user-access-token'  # optional; normally derived from TW_URT at runtime
