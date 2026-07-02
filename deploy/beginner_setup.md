# Beginner's Setup Guide

This walks through setting up your own copy of this bot from scratch, assuming you've never used
a terminal, Linux, or git before. It covers everything from writing an operating system onto a
Raspberry Pi through having the bot running permanently in Discord.

If you're already comfortable with terminals and Linux, the shorter
[setup_pi.md](setup_pi.md) covers the same ground faster.

**Time needed:** 45-60 minutes. **You'll need:** a Raspberry Pi 5 (4GB or more), a microSD card
(16GB or larger) and a way to plug it into your everyday computer (many laptops have a slot built
in; otherwise a cheap USB adapter works), a Discord account, and an internet connection.

## Step 1: Write the operating system onto your Raspberry Pi

1. On your everyday computer, download and install
   [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Put the microSD card into your computer.
3. Open Raspberry Pi Imager.
4. Click **Choose Device** and pick **Raspberry Pi 5**.
5. Click **Choose OS**, then **Raspberry Pi OS (other)**, then **Raspberry Pi OS Lite (64-bit)**.
   The "Lite" version skips the desktop, which is what you want here - the bot is controlled
   entirely through Discord and a terminal, and skipping the desktop leaves more of the Pi's
   limited memory for running the bot and its local AI model.
6. Click **Choose Storage** and select your microSD card. Double check you've picked the right
   one - this next step erases it.
7. Click the gear icon (bottom right) to open **OS Customisation** before writing. This lets you
   set everything up in advance so you never need to plug a monitor or keyboard into the Pi:
   - **General tab**: set a hostname (e.g. `musicbot`), and a username and password you'll
     remember - you'll use these to log in remotely.
   - **General tab**: if you're not using a wired ethernet cable, fill in your WiFi network name
     and password.
   - **Services tab**: turn on **Enable SSH**, and choose "Use password authentication".
   - Click **Save**.
8. Click **Write**, confirm, and wait for it to finish (a few minutes).
9. Put the microSD card into the Raspberry Pi and plug in power. Wait about 2 minutes for it to
   boot for the first time.

## Step 2: Connect to your Pi

Everything from here happens by typing commands into a window on your own computer that get sent
to the Pi over your network - called "SSH". You never need to plug anything into the Pi itself.

**On Windows:**
1. Press the Windows key, type `powershell`, and open **Windows PowerShell**.
2. Type (replacing `yourusername` and `musicbot` with what you set in Step 1):
   ```
   ssh yourusername@musicbot.local
   ```
   and press Enter.
3. The first time, it'll ask whether to trust the connection - type `yes` and press Enter.
4. Enter the password from Step 1 when prompted. **Nothing will appear as you type** (no dots,
   no cursor movement) - that's normal, just type the password and press Enter.

**On Mac:** open the **Terminal** app (search for it with Spotlight, `Cmd+Space`) and use the same
`ssh` command as above.

You'll know it worked when your prompt changes to show something like `yourusername@musicbot:~ $`.

**If `musicbot.local` doesn't connect:** your network may not support that shortcut. Find the
Pi's IP address instead by checking your router's admin page (usually lists connected devices) or
using a phone app like [Fing](https://www.fing.com/), then connect with
`ssh yourusername@<that IP address>` instead.

## Step 3: A quick terminal primer

A few things that'll help for the rest of this guide:
- Commands are case-sensitive and usually need to be typed (or pasted) exactly.
- To paste into PowerShell, right-click inside the window (or `Ctrl+Shift+V`).
- `sudo` before a command means "run this with administrator privileges" - you may be asked for
  your password again.
- You'll need to edit a couple of files using a simple in-terminal text editor called `nano`.
  When a step says to run `nano somefile`, a text editor opens up:
  - Use the arrow keys to move around and type normally to edit.
  - Press `Ctrl+O` then `Enter` to save.
  - Press `Ctrl+X` to exit back to the terminal.

## Step 4: Install required software

Copy and paste each block below one at a time, pressing Enter after each and waiting for it to
finish before moving to the next.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg git unzip
```

Install Deno (lets the bot reliably extract audio from YouTube):

```bash
curl -fsSL https://deno.land/install.sh | sh
echo 'export PATH="$HOME/.deno/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
deno --version
```

You should see a version number printed - that confirms it installed correctly.

Install Ollama (runs the local AI model) and download a small model for it to use:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:1.5b
```

The model download is about 1GB and may take a few minutes depending on your internet speed.

## Step 5: Download the bot's code

1. In a web browser, go to this project's GitHub page.
2. Click the green **Code** button, make sure **HTTPS** is selected, and click the copy icon next
   to the URL shown.
3. Back in your Pi's terminal, run:
   ```bash
   git clone <paste the URL you just copied> discord-music-bot
   cd discord-music-bot
   ```
4. Set up the bot's Python environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Step 6: Create your Discord bot

This creates the actual Discord "bot" that will join your server - it's owned by your Discord
account, separate from anyone else's.

1. In a browser, go to the [Discord Developer Portal](https://discord.com/developers/applications)
   and log in with your normal Discord account.
2. Click **New Application** (top right), give it a name (this is what shows up in Discord - you
   can change it later), and create it.
3. In the left sidebar, click **Bot**. A bot user should already be created automatically.
4. Scroll down to **Privileged Gateway Intents** and turn on **Message Content Intent**. This is
   required for the bot to understand messages where you `@mention` it.
5. Near the top of the **Bot** page, find the button to reveal/copy the bot's **token**. Click it
   and copy the token somewhere safe temporarily (like a plain text file) - you'll paste it into
   the Pi in the next step. Treat this like a password: never share it or post it publicly. If it
   ever leaks, come back here and reset it.
6. In the left sidebar, click **OAuth2**, then scroll to **OAuth2 URL Generator**.
7. Under **Scopes**, check `bot` and `applications.commands`.
8. A **Bot Permissions** box appears below - check `Send Messages`, `Embed Links`,
   `Read Message History`, `Connect`, and `Speak`. `Embed Links` is easy to miss but required -
   without it, the now playing panel silently fails to post.
9. Scroll down, copy the **Generated URL**, paste it into a new browser tab, pick your Discord
   server, and click **Authorize**. The bot will now appear (offline) in your server's member
   list.

## Step 7: Configure and test the bot

Back in your Pi's terminal (make sure you're still in the `discord-music-bot` folder):

```bash
cp .env.example .env
nano .env
```

This opens the config file in the editor. Replace the empty value after `DISCORD_BOT_TOKEN=` with
the token you copied in Step 6 (paste with right-click or `Ctrl+Shift+V`), so the line looks like:

```
DISCORD_BOT_TOKEN=the-long-token-you-copied
```

Save (`Ctrl+O`, `Enter`) and exit (`Ctrl+X`).

Now run the bot manually to make sure everything works:

```bash
python -m bot.main
```

Check Discord - the bot should now show as online. Try `/play` with a song name in a server text
channel while you're in a voice channel. Slash commands sometimes take a minute or two to show up
the very first time.

Once you've confirmed it works, press `Ctrl+C` in the terminal to stop it - the next step sets it
up to run permanently in the background instead.

## Step 8: Keep the bot running permanently

This installs the bot as a background service that starts automatically, including after the Pi
reboots. Run these commands exactly as shown - they automatically fill in your actual username and
folder path, so there's nothing to edit by hand:

```bash
sed -e "s/User=pi/User=$(whoami)/" -e "s#/home/pi#$HOME#g" deploy/discord-bot.service | sudo tee /etc/systemd/system/discord-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now discord-bot.service
sudo systemctl status discord-bot.service
```

The status output should say `active (running)` in green. Press `q` to exit the status view.

To watch the bot's live logs at any point (useful for troubleshooting):

```bash
journalctl -u discord-bot.service -f
```

Press `Ctrl+C` to stop watching (this doesn't stop the bot itself).

## Step 9 (optional but recommended): keep yt-dlp updated automatically

The bot relies on a tool called yt-dlp to pull audio from YouTube. YouTube periodically changes
things that break older versions of it, more often than the bot's other components change.

The bot already reacts to this on its own: if 3 songs in a row fail to play, it'll post a message
about it, try updating yt-dlp right then, and restart itself automatically if that fixed it -
nothing to set up for that part. What this step adds is a weekly check that updates yt-dlp
proactively, so most breakage never has a chance to happen in the first place:

```bash
sed -e "s/User=pi/User=$(whoami)/" -e "s#/home/pi#$HOME#g" deploy/yt-dlp-update.service | sudo tee /etc/systemd/system/yt-dlp-update.service
sudo cp deploy/yt-dlp-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yt-dlp-update.timer
```

## Troubleshooting

- **Bot shows offline in Discord.** Run `sudo systemctl status discord-bot.service`. If it says
  `failed`, run `journalctl -u discord-bot.service -n 50` to see the error. A common cause is a
  typo in the token in `.env` - re-open it with `nano .env` and check.
- **`command not found` for `git`, `python3`, `ffmpeg`, etc.** Re-run the install command from
  Step 4 - one of the packages may not have installed successfully.
- **Slash commands don't show up in Discord.** Wait a few minutes and try again, or try kicking
  and re-inviting the bot using the invite link from Step 6.
- **`/play` gets stuck on "thinking..." and never responds.** This usually means the bot is
  missing the `Embed Links` permission in that server, so it can't post the now playing panel.
  Fix it without re-inviting: go to **Server Settings > Roles**, click the bot's role, and enable
  `Embed Links`. (Music will actually still play even with this missing - only the persistent Now
  Playing panel is affected - but it's worth fixing.)
- **No sound when playing.** The audio streams directly to whoever's in the Discord voice channel
  on their own device - you don't need speakers connected to the Pi itself. Check
  `journalctl -u discord-bot.service -f` while running `/play` for errors from `ffmpeg` or
  `yt-dlp`.
- **Something changed and you want to update the bot later:**
  ```bash
  cd ~/discord-music-bot
  git pull
  source .venv/bin/activate
  pip install -r requirements.txt
  sudo systemctl restart discord-bot.service
  ```
