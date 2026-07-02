import os

# Settings() requires DISCORD_BOT_TOKEN at import time; provide a dummy so tests
# don't depend on a local .env file being present (e.g. in CI).
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
