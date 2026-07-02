# Discord Music Bot

A Discord bot that streams audio from YouTube into a voice channel, controllable with slash
commands or natural language routed through a locally-hosted LLM (Ollama).

## Features

- `/join`, `/leave` - voice channel management
- `/play <query>`, `/pause`, `/resume`, `/skip`, `/queue` - direct playback control
- `/ask <message>` or `@bot <message>` - natural language control via a local Ollama model
  (e.g. "play something chill for studying")
- A live "now playing" panel that reposts itself at the bottom of the channel as the queue changes
- Playback control commands require being in the bot's voice channel once a session is active, so
  someone elsewhere in the server can't hijack a session they're not part of

## How it works

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) resolves a search query to a direct, streamable audio
  URL.
- `discord.py`'s `FFmpegPCMAudio` pipes that stream (via `ffmpeg`) straight into the voice channel.
- A small local model served by [Ollama](https://ollama.com) (default: `qwen2.5:1.5b`) interprets
  free-text requests. It uses Ollama's structured output mode to decide which playback function to
  call (if any) as a schema-constrained JSON object, then dispatches to the same functions the
  slash commands use.

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

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Deploying to a Raspberry Pi

See [deploy/setup_pi.md](deploy/setup_pi.md) for a full walkthrough, including creating the
Discord bot application and running the bot as a systemd service alongside Ollama.

## Security & privacy considerations

- **Never commit `.env`.** It holds your bot token; `.gitignore` already excludes it, and
  `.env.example` should stay a blank template.
- **Message Content intent.** The `@mention` chat path requires Discord's privileged Message
  Content intent, meaning the bot receives the text of messages in channels it can see (not just
  ones directed at it) in order to detect mentions. No message content is logged or stored.
- **Remote code fetched at runtime.** `bot/music/youtube.py` enables yt-dlp's
  `remote_components: ["ejs:github"]`, which lets yt-dlp download a small JavaScript
  challenge-solving script from the official
  [yt-dlp-ejs](https://github.com/yt-dlp/yt-dlp-ejs) GitHub repo when needed to keep up with
  YouTube's playback-signature checks. This is scoped to GitHub only (not npm) to keep the set of
  trusted sources narrow, but it is still remotely-fetched code executing on your machine - review
  that project if you want to vet it yourself.
- **All LLM processing is local.** Natural-language requests are sent to your own Ollama instance,
  never to a third-party AI API.
- **No secrets in this repo's git history** (verified via `git log -p` across all tracked files)
  and no server-specific hostnames/paths are committed - `deploy/discord-bot.service` and
  `deploy/setup_pi.md` use generic placeholders you fill in yourself.
- **Command access is per-server only**, not per-user beyond the voice-channel check above -
  anyone with access to invite the bot controls what it can do in their server.

## License

[MIT](LICENSE)
