# AinBot Music + VC Only

This is the separate bot that only loads music and voice channel tools.

## Loaded Command Groups

- `/music`
- `/jtc`
- `/vc`
- `/theme`
- `/help`
- `/sync`

## Main Commands

- `/music join`
- `/music panel`
- `/music add`
- `/music play`
- `/music queue`
- `/music info`
- `/music helpers`
- `/music helpers_join`
- `/music helpers_leave`
- `/jtc setup`
- `/jtc disable`
- `/vc claim`
- `/vc rename`
- `/vc lock`
- `/vc unlock`
- `/vc hide`
- `/vc reveal`
- `/vc limit`
- `/vc bitrate`
- `/vc drag`
- `/vc permit`
- `/vc reject`
- `/vc transfer`
- `/vc godmode`
- `/vc godmodeoff`
- `/vc godmodelist`
- `/vc leaderboard`
- `/theme color`
- `/theme banner`
- `/theme effects`
- `/theme preview`
- `/sync`

## Prefix Commands

- `,drag old voice to new voice`
- `,dragall old voice to new voice`
- `,moveall old voice to new voice`
- `,musicpanel`
- `,join`
- `,addsong song name`
- `,play`
- `,songinfo`
- `,musicbots`
- `,musicbots join 10`
- `,musicbots leave`
- `,theme color glassred`
- `,theme banner <image-or-gif-link>`
- `,theme effects on`
- `,ainrename new name`
- `,ainprof` with an attached image

## Railway Variables

```env
DISCORD_TOKEN=your-new-vc-music-bot-token
DATABASE_URL=sqlite:///data/vc_music_bot.sqlite3
DEFAULT_PREFIX=,
OWNER_IDS=your_discord_user_id
LOG_LEVEL=INFO
ENABLE_MUSIC=true
AUTO_SYNC_COMMANDS=true
MUSIC_HELPER_TOKENS=
YTDLP_SEARCH_PROVIDER=ytsearch
YTDLP_COOKIES_FILE=
YTDLP_COOKIES_TEXT=
FFMPEG_PATH=
OPUS_PATH=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
```
