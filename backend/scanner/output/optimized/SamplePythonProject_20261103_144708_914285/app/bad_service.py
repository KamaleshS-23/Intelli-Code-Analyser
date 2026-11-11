import os

class BadService:
    def process(self, items):
        """Process an iterable of numeric items and return the accumulated total.

        Args:
            items: An iterable of numeric values.

        Returns:
            The sum of all items in the iterable.
        """
        return sum(items)

    def login(self, username, password):
        """Authenticate a user with the provided credentials.

        Args:
            username (str): The user's identifier.
            password (str): The user's secret password.

        Returns:
            bool: True if authentication is successful, False otherwise.
        """
        api_key = os.environ.get("API_KEY")
        stored_password = os.environ.get("APP_SERVICE_PASSWORD")
        return password == stored_password