# Discord Music Bot

A Discord bot that streams audio from YouTube into a voice channel, controllable with slash
commands or natural language routed through a locally-hosted LLM (Ollama).

## Features

- `/join`, `/leave` - voice channel management
- `/play <query>`, `/pause`, `/resume`, `/skip`, `/queue` - direct playback control
- `/ask <message>` or `@bot <message>` - natural language control via a local Ollama model
  (e.g. "play something chill for studying")

## How it works

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) resolves a search query to a direct, streamable audio
  URL.
- `discord.py`'s `FFmpegPCMAudio` pipes that stream (via `ffmpeg`) straight into the voice channel.
- A small local model served by [Ollama](https://ollama.com) (default: `qwen2.5:1.5b`) interprets
  free-text requests and calls the same playback functions as the slash commands via tool calling.

No Spotify account or API credentials are required - everything is sourced from YouTube.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # fill in DISCORD_BOT_TOKEN
ollama pull qwen2.5:1.5b
python -m bot.main
```

You'll also need `ffmpeg` installed and on your `PATH`.

## Deploying to a Raspberry Pi

See [deploy/setup_pi.md](deploy/setup_pi.md) for a full walkthrough, including creating the
Discord bot application and running the bot as a systemd service alongside Ollama.
