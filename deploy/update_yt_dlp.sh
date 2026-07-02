#!/bin/bash
# Keeps yt-dlp current. YouTube regularly changes things in ways that break
# older yt-dlp versions - unlike the rest of requirements.txt, this one
# dependency needs to move faster than a manual "pip install -r" habit
# would catch. Run on a schedule via yt-dlp-update.timer.
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

before=$(pip show yt-dlp | awk '/^Version:/{print $2}')
pip install --quiet --upgrade yt-dlp
after=$(pip show yt-dlp | awk '/^Version:/{print $2}')

if [ "$before" = "$after" ]; then
    echo "yt-dlp already up to date ($before)"
    exit 0
fi

echo "yt-dlp updated: $before -> $after, restarting the bot to pick it up"
# No sudo needed: killing our own process is enough, since discord-bot.service
# is configured with Restart=on-failure and brings it straight back up.
pkill -u "$(whoami)" -f "bot.main"
