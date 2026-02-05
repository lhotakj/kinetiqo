from flask_login import UserMixin

# Mock User Database
users = {
    "jarda": {"password": "jarda"}
}

class User(UserMixin):
    def __init__(self, id):
        self.id = id
