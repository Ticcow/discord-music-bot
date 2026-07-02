# Discord Music Bot

A Discord bot that streams audio from YouTube into a voice channel. Control it with direct slash
commands, or talk to it in plain English and let a locally-hosted LLM (via [Ollama](https://ollama.com))
figure out what you want. No Spotify account, API keys, or third-party AI service required -
everything runs from YouTube and your own machine.

## Commands

| Command | What it does |
| --- | --- |
| `/join` | Connects the bot to your current voice channel and posts the [now playing panel](#the-now-playing-panel). |
| `/leave` | Disconnects the bot, clears the queue, and removes the panel. |
| `/play <query>` | Searches YouTube for a specific song/artist and queues it to play **next** - ahead of anything already queued by `/ask`. Starts playing immediately if nothing else is. |
| `/pause` | Pauses the current track. |
| `/resume` | Resumes a paused track. |
| `/skip` | Skips to the next queued track. |
| `/queue` | Shows what's currently playing and what's up next. |
| `/ask <message>` | Natural-language control - e.g. *"play something chill for studying"* or *"what's playing?"*. A local LLM decides which action to take. |
| `@BotName <message>` | Same as `/ask`, but by mentioning the bot in a message instead of using a slash command. |

Once a session is active, all playback control commands (`/play`, `/pause`, `/resume`, `/skip`,
`/ask`) require you to be in the bot's voice channel - someone elsewhere in the server can't
hijack a session they're not part of. `/join`, `/leave`, and `/queue` stay open to everyone.

### Natural language examples

- *"play some early 2000s hip hop"* - searches and queues a short batch of matching tracks
- *"pause the music"*
- *"skip this"*
- *"what's playing right now?"*

### Two queue lanes

Tracks queue into one of two lanes:

- **Priority** (`/play`) - plays next, in the order requested.
- **Ambient** (`/ask` vibe/artist requests) - queues a short batch of related tracks (3 by
  default) for a listening session, and yields to anything in the priority lane.

A `/play` request always "leapfrogs" ahead of whatever's left in an ambient batch, so you're never
stuck waiting through someone else's autoplay session to hear the specific song you asked for.

### Auto-disconnect

The bot leaves the voice channel automatically, clearing the queue and posting a note explaining
why, in two situations:

- **Idle timeout** - nothing has actively played (empty queue, or paused) for 10 minutes.
  Configurable via `IDLE_TIMEOUT_SECONDS` in `.env`.
- **Alone in the channel** - every human member leaves, whether or not anything was playing.

## The Now Playing panel

The first time the bot joins a voice channel in a server, it posts a live status panel to that
text channel showing:

- **Now Playing** - the current track and who requested it (or "Paused")
- **Up Next** - the next several queued tracks, in play order

The panel updates itself automatically whenever something changes - a track starts, something
gets queued, playback is paused or resumed - by reposting itself at the bottom of the channel and
deleting the old version. That keeps it visible as the most recent message instead of sinking
under newer chat. It's removed when the bot leaves the voice channel (`/leave`).

## How it works

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) searches YouTube and resolves the winning result to a
  direct, streamable audio URL. Plain search results often mix in podcasts, interviews, and
  reaction videos alongside real tracks, so searches pull a wider candidate pool and filter out
  anything that looks like talk content by duration and title/channel keywords, preferring
  official artist "Topic" channels (YouTube's auto-generated, music-only channels) when available.
- `discord.py`'s `FFmpegPCMAudio` pipes that stream (via `ffmpeg`) straight into the voice channel.
- A small local model served by Ollama (default: `qwen2.5:1.5b`) interprets free-text requests. It
  uses Ollama's structured output mode to decide which playback function to call (if any) as a
  schema-constrained JSON object, then dispatches to the same functions the slash commands use.

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

## Legal

This project uses `yt-dlp` to extract and stream audio from YouTube, which falls outside
YouTube's official API and Terms of Service. This tool is intended for personal and educational
use. You are responsible for complying with YouTube's Terms of Service, Discord's Developer Policy,
and applicable copyright law in your jurisdiction when running it. This project is not affiliated
with, endorsed by, or sponsored by YouTube, Google, or Discord.

## License

[MIT](LICENSE)
