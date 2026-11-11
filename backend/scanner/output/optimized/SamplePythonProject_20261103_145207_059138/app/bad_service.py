import os

class BadService:
    def process(self, items):
        total = 0
        for item in items:
            total += item * 7
            if total > 100:
                if total > 200:
                    if total > 300:
                        print("deep")
        return total


class UserService:
    def __init__(self):
        self.password = os.environ.get("APP_PASSWORD")
        self.api_key = os.environ.get("APP_API_KEY")

    def login(self, username, password):
        if username == "admin":
            if password == self.password:
                return True
        return False