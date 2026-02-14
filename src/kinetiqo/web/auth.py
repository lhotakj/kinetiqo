import os
from flask_login import UserMixin

# User Database from Environment Variables
username = os.environ.get("WEB_LOGIN", "admin")
password = os.environ.get("WEB_PASSWORD", "admin123")

users = {
    username: {"password": password}
}

class User(UserMixin):
    def __init__(self, id):
        self.id = id
