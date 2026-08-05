# All-in-One Discord Bot

A production-oriented Discord bot for Python 3.12+ and discord.py 2.x. It includes slash commands, prefix commands, per-server prefixes, moderation, automod, anti-nuke protection, god mode, tickets, reaction/self roles, welcome messages, leveling, giveaways, economy, music controls, utility tools, logging, backups, and interactive help/config flows.

The project pins `discord.py[voice]==2.7.1`, the current 2.x release on PyPI as of August 3, 2026.

## Quick Start

1. Install Python 3.12 or newer.
2. Copy `.env.example` to `.env`.
3. Put your Discord bot token in `.env`.
4. Install dependencies:

```powershell
py -3.12 -m pip install -r requirements.txt
```

5. Run the bot:

```powershell
py -3.12 -m bot
```

Windows helper:

```powershell
.\scripts\run.ps1
```

Linux/macOS helper:

```bash
bash scripts/run.sh
```

## Discord Developer Portal Setup

Enable these privileged gateway intents for the bot application:

- Server Members Intent
- Message Content Intent

Invite the bot with `bot` and `applications.commands` scopes. Give it the permissions needed for the modules you use.

## Storage

SQLite is used by default at `data/bot.sqlite3`. Set `DATABASE_URL=postgres://user:pass@host:5432/dbname` for PostgreSQL. SQLite is the most convenient default; PostgreSQL is recommended for very large communities.

## Music Notes

Music commands use `yt-dlp` and Discord voice support. Some platforms limit bot playback or require API access. Spotify URLs are resolved as metadata/search terms when credentials are present; playback still uses legally available audio sources.

If YouTube or YouTube Music says sign-in/cookies are required, add either `YTDLP_COOKIES_FILE` or `YTDLP_COOKIES_TEXT` in Railway Variables. `YTDLP_COOKIES_TEXT` should contain a Netscape-format cookies.txt export. Treat it like a password.

The bot includes `imageio-ffmpeg` so music can still play if Railway does not expose the system `ffmpeg` command. Advanced users can override it with `FFMPEG_PATH`.

## Main Commands

- `/help` or `!help`: interactive help
- `/config panel`: server configuration UI
- `/prefix set`: change prefix
- `/mod ban`, `/mod kick`, `/mod timeout`, `/mod warn`, `/mod purge`
- `/automod configure`: anti-spam/link/invite/caps/profanity settings
- `/antinuke configure`: protection thresholds and punishments
- `/godmode add`: protect users or roles
- `/ticket panel`: create ticket panels
- `/roles panel`: self-role panel
- `/welcome configure`: welcome/goodbye/autorole settings
- `/level rank`: XP rank card
- `/giveaway start`: timed giveaways
- `/economy daily`: economy system
- `/music add`: add audio to the queue
- `/music play`: start the queued audio
- `/utility ping`, `/utility userinfo`, `/utility poll`, `/utility qr`

## Backups

Database backups are written to `data/backups` on an interval controlled by `BACKUP_INTERVAL_MINUTES`.
