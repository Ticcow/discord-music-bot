# Raspberry Pi 5 (4GB) setup

New to terminals, Linux, or git? Follow [beginner_setup.md](beginner_setup.md) instead - it covers
the same setup with no assumed experience, including flashing the SD card and connecting over SSH
for the first time.

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg git unzip
```

`yt-dlp` increasingly needs a JavaScript runtime to decipher YouTube's signatures reliably (you'll
see a `No supported JavaScript runtime could be found` warning without one, and some formats may
fail to resolve). Install [Deno](https://deno.com) (supports Linux aarch64, i.e. the Pi 5) to
cover this:

```bash
curl -fsSL https://deno.land/install.sh | sh
echo 'export PATH="$HOME/.deno/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
deno --version
```

## 2. Install Ollama and pull a small model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:1.5b
```

Confirm it runs and check idle memory usage before moving on:

```bash
ollama run qwen2.5:1.5b "say hi"
free -h
```

## 3. Get the bot code onto the Pi and set up a virtualenv

```bash
cd /home/pi
git clone <your-repo-url> discord-music-bot
cd discord-music-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Create a Discord bot application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**. Name it whatever you like.
2. In the **Bot** tab, click **Add Bot**. Under **Privileged Gateway Intents**, enable **Message Content Intent** (needed so the bot can read `@mention` chat messages for the `/ask`-style natural language path).
3. Still in the **Bot** tab, click **Reset Token** / **Copy** to get your bot token. Keep this secret - it goes in `.env` as `DISCORD_BOT_TOKEN`.
4. In the **OAuth2 > URL Generator** tab, check the `bot` and `applications.commands` scopes, then under **Bot Permissions** check: `Send Messages`, `Read Message History`, `Connect`, `Speak`.
5. Copy the generated URL, open it in a browser, and invite the bot to your server.

## 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
DISCORD_BOT_TOKEN=<token from step 4>
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b
```

## 6. Run it manually first

```bash
source .venv/bin/activate
python -m bot.main
```

Slash commands can take up to an hour to appear globally the first time; they usually show up within a minute or two in practice. Test `/join`, `/play <song>`, `/queue`, `/skip`, `/pause`, `/resume`, `/leave`, and `/ask`.

## 7. Install as a systemd service (auto-start on boot)

Edit `deploy/discord-bot.service` if your username or install path differs from `pi` / `/home/pi/discord-music-bot`, then:

```bash
sudo cp deploy/discord-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now discord-bot.service
sudo systemctl status discord-bot.service
journalctl -u discord-bot.service -f
```

## 8. Check resource headroom under load

While the bot is playing audio and `ollama` is loaded, check:

```bash
free -h
htop
```

If memory is too tight, drop to a smaller model (e.g. `qwen2.5:0.5b`) by changing `OLLAMA_MODEL` in `.env` and restarting the service.
