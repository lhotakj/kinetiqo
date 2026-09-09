import os

from flask_login import UserMixin

# User Database from Environment Variables
username = os.environ.get("WEB_LOGIN", "admin")
password = os.environ.get("WEB_PASSWORD", "admin123")

users = {
    username: {"password": password}
}


class User(UserMixin):
    """Simple Flask-Login User wrapper used by the demo web UI.

    The project uses a minimal in-memory user store populated from
    environment variables for demo purposes. In production replace with a
    proper user table and secure password hashing.
    """
    def __init__(self, id):
        """Create a User with the given identifier.

        Args:
            id (str): The user's identifier (username).
        """
        self.id = id
