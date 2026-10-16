import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "my_secret_key_change_me")
