"""Streaming lib"""

import requests

class Tw:
    """Basic API client"""
    def __init__(self, url, client_id, app_access_token, user_access_token, login):
        # Set up variables for API request
        self.client_id = client_id
        self.app_access_token = app_access_token
        self.user_access_token = user_access_token
        self.url = url
        self.login = login
        self.user_id = None
    def get(self, url, params, user=False):
        """Make GET request"""
        token = self.app_access_token
        if user:
            token = self.user_access_token
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
    def followed(self):
        """Get live streams"""
        return self.get('streams/followed',
                        params={'user_id': self.get_user_id()},
                        user=True)['data']
