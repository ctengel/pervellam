"""Streaming lib"""

import requests

class Tw:
    """Basic API client"""
    def __init__(self, url, client_id, app_access_token, user_refresh_token, login, id_url, client_secret):
        # Set up variables for API request
        self.client_id = client_id
        self.app_access_token = app_access_token
        self.user_refresh_token = user_refresh_token
        self.url = url
        self.login = login
        self.user_id = None
        self.user_access_token = None
        self.id_url = id_url
        self.client_secret = client_secret
    def get(self, url, params, user=False):
        """Make GET request"""
        token = self.app_access_token
        if user:
            token = self.get_user_access_token()
        response = requests.get(self.url + url,
                                headers={"Client-ID": self.client_id,
                                         "Authorization": f"Bearer {token}"},
                                params=params)
        response.raise_for_status()
        return response.json()
    def get_user_id(self):
        """Return numeric user ID based on login"""
        if self.user_id:
            return self.user_id
        self.user_id = self.get('users', params={'login': self.login})["data"][0]["id"]
        return self.user_id
    def get_user_access_token(self):
        """Convert refresh token to access token"""
        if self.user_access_token:
            return self.user_access_token
        self.user_access_token = requests.post(self.id_url,
                                               data={"client_id": self.client_id,
                                                     "client_secret": self.client_secret,
                                                     "grant_type": "refresh_token",
                                                     "refresh_token": self.user_refresh_token}).json()["access_token"]
        return self.user_access_token
    def followed(self):
        """Get live streams"""
        return self.get('streams/followed',
                        params={'user_id': self.get_user_id()},
                        user=True)['data']
