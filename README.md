# Lidarr.Plugin.YoutubeMusic

A native Lidarr plugin (installs under **System → Plugins**) that syncs your
**YouTube Music** liked songs / playlist into Lidarr as artists + albums, and
optionally triggers album searches so Lidarr manages the FLACs.

It schedules the sync **inside Lidarr** (no external Task Scheduler needed) and
executes the proven, Python-based sync engine from this repo.

> **Headline:** plugins can hold a UI-managed schedule in-app. This plugin
> registers a scheduled task (Settings → Metadata) with a configurable
> interval, plus a settings surface under Settings → Connect.

## Quick install (recommended)

1. In Lidarr: **System → Plugins**, paste this repository's URL and choose **Install**:
   `https://github.com/smacca20/Lidarr.Plugin.YoutubeMusic`
2. **Restart Lidarr** to load the plugin.
3. Configure under **Settings → Metadata → "YouTube Music Sync Scan"** (see
   [Configure](#configure)), then run it from **System → Tasks**.

> Requires plugin-capable Lidarr (**`develop`/`nightly`, ≥ 3.1.2.4938**). System → Plugins
> installs the latest **GitHub Release** (built automatically by this repo's CI from `main`).
> Building the plugin yourself is optional — see [Build from source](#build-from-source-optional).

## How it works

```
Lidarr (in-process)
  ├─ Settings → Connect  "YouTube Music Sync"  (YoutubeMusicNotification)
  │     └ stores config: python path, project path, CLI args
  ├─ Settings → Metadata "YouTube Music Sync Scan"  (YoutubeMusicSyncTask)
  │     └ registers a ScheduledTask row (interval from settings)
  └─ Scheduler fires →
       YoutubeMusicSyncCommand → Executor
            └─ shells out:  python -m ytmusic_lidarr_sync --search
                 (the Python engine bundled in `sync/` + its config.ini)
```

## Sync engine & behavior (what a run does)

The plugin runs the bundled Python engine (`sync/ytmusic_lidarr_sync`) against YouTube
Music + Lidarr:

```
YT Music -> track {title, artist(s), album}
  -> resolve ARTIST     (exact normalized-name match; none => skipped to "Unmatched")
  -> add artist if missing  (whole discography imported, UNMONITORED)
  -> resolve ALBUM/SINGLE  (the matched track's album inside that artist)
  -> MONITOR only the matched album/single   (if "Monitor matched albums & singles" = ON)
  -> AlbumSearch that album                   (if CLI args include --search)
```

**Matching is conservative:**
- Artists must match by **exact normalized name** (no fuzzy fallback — a near-miss like
  `Stefen Hauk` is **not** added as `Stefan`). Same-named artists are disambiguated by the
  track's album, then title. If several same-named artists match and **none** is clearly
  corroborated (e.g. an ambiguous "Martin Miller"), the track is skipped and reported as
  **ambiguous** — the sync **never auto-adds a random same-named artist**.
- Editions map back to the base album: YT's `MTV Unplugged (Live)` matches Lidarr's `MTV
  Unplugged` (earlier editions match too). When an artist has several same-titled releases,
  the YT track's **release year** (when YT provides one) is used as a tie-breaker to prefer
  the right edition. The artist is **always name-verified**, so a different artist's
  same-titled album (e.g. Nirvana's `MTV Unplugged`) is never attached to a Pearl Jam track.
- Albums/singles are matched by normalized title against the artist's Lidarr albums (with a
  MusicBrainz fallback). Matched ones are shown under **Albums matched** and **monitored**;
  unmatched albums are listed under **Albums not found** and left unmonitored (artist still added).

**Monitoring model:** new artists are added with their discography present but **unmonitored**;
only the **albums/singles that matched a liked track** are monitored (and searched). Everything
else in the artist's catalog stays unmonitored. **Pre-existing artists are never retroactively
changed.**

**Where the output shows:** the full SYNC REPORT (items seen, artists added, albums matched /
not found, unmatched, exit code) is set as the command's **completion message**, so it appears
in **System → Tasks** after a run — no need to open the log files. (This Lidarr build's command
API has no live line-streaming, so the full report shows on completion.)

### Config reference (`/app/sync/config.ini`, or a mounted `/config/.../config.ini`)

`[lidarr]` — `url` (default `http://localhost:8686`), `port` (auto from `config.xml`), `api_key`
(auto from `config.xml`), `root_folder`, `quality_profile` (**by name**, blank = auto → Lossless),
`metadata_profile` (**by name**, blank = auto → Standard), `album_folder`, `monitor_albums`
(monitor **only matched** albums/singles), `monitored` (monitor new artists).

`[ytmusic]` — `headers_file`, `auth` (raw cookie / path / JSON), `oauth_client_id`,
`oauth_client_secret`, `oauth_token_file`.

### CLI usage (from the sync dir)

```bash
python -m ytmusic_lidarr_sync --search          # add + monitor matched + AlbumSearch
python -m ytmusic_lidarr_sync --add --no-monitor-albums
python -m ytmusic_lidarr_sync --oauth-login     # one-time OAuth device flow
python -m ytmusic_lidarr_sync --dump report.json
```

Flags: `--add`, `--search`, `--monitor-albums/--no-monitor-albums`, `--monitored/--no-monitored`,
`--quality-profile NAME|ID`, `--metadata-profile NAME|ID`, `--playlist`, `--playlists`,
`--limit`, `--dump`, `--oauth-login`.

> **Limits & rate limiting:** each playlist / liked list is read up to `--limit` (**default 200**;
> add `--limit 0` to the CLI arguments for the entire source). A small delay + retry/backoff
> (`request_delay_sec`, default `0.2`) avoids YouTube Music 429 throttling on large playlists.

## Prerequisites

- **Lidarr 3.1.2.4938+ on the `develop` or `nightly` branch** (the `master`
  branch does not support plugins).
- **YouTube Music auth** — pasted into the plugin's auth field (cookie or OAuth; see
  [Configure](#configure)). No Python install needed: the sync engine is bundled in
  `sync/` (and already inside the baked image), so Lidarr runs it itself.
- **.NET 8 SDK** — only if you **build from source** (see
  [Build from source](#build-from-source-optional)); the quick install needs no build.

## Build from source (optional)

Most users won't need this — **use [Quick install](#quick-install-recommended)**, which pulls
the pre-built plugin from this repo's GitHub Release (built by CI on every `main` push). Build
from source only if you're compiling the plugin yourself or working on a fork:

```bash
cd plugin/Lidarr.Plugin.YoutubeMusic
python scripts/prepare-lidarr.py   # downloads pinned Lidarr reference binaries
dotnet build src/Lidarr.Plugin.YoutubeMusic/Lidarr.Plugin.YoutubeMusic.csproj \
    -c Release -p:PluginVersion=0.1.0
```

The output zip is `_temp/bin/Release/Lidarr.Plugin.YoutubeMusic/Lidarr.Plugin.YoutubeMusic.net8.0.zip`.
The included GitHub Action (`<repo>/.github/workflows/build.yml`) does the same build and
attaches the zip to a GitHub **Release** on `main`.

Installing a build: if you forked this repo, point the Quick install URL at your fork (edit
`Owner`/`GithubUrl` in `Plugin.cs`), or extract the built zip into Lidarr's
`Plugins/<owner>/<name>/` folder and restart Lidarr.

## Configure

1. **Settings → Metadata → "YouTube Music Sync Scan"** — this is the entry that
   drives everything (the scheduled task). Configure it **here** (see note below
   on the auth cookie):
   - **Python executable**: `/usr/bin/python3` (baked into the image; defaults automatically)
   - **Sync project path**: `/app/sync` (baked image) or `/config/...` (mounted) — auto-detected
   - **CLI arguments**: `--search` (add + monitor matched + AlbumSearch), `--add`, or empty for dry-run
   - **Monitored (default for new artists)**: checkbox, default ON
   - **Monitor matched albums & singles**: checkbox, default ON (monitors ONLY matched releases)
   - **Quality Profile (name)** / **Metadata Profile (name)**: blank = auto (Lossless / Standard)
   - **Scan interval (minutes)**: how often to run (minimum 60)
   - Ensure the entry is **enabled** (an enabled entry registers the scheduled task).
2. Optional: **Settings → Connect → + → "YouTube Music Sync"** — a settings surface
   with a **Test** button. Not required for running; the scheduled entry above is
   the source of truth.

> **Authenticating (in-memory cookie):** the sync needs YouTube Music auth for
> liked songs. The simplest, no-file method: in the Lidarr UI (on the entry above)
> set **"YouTube Music cookie (auth)"** to the full `Cookie` header value from a
> logged-in `music.youtube.com` session (DevTools → Network → any request →
> Request Headers → Cookie). The plugin holds it **in memory** and passes it to the
> sync process via an **environment variable** (ephemeral — never written to disk).
> Leave it empty to use a `headers.json` file on the `headers_file` config path
> instead. Cookies can expire; re-paste when rejected.

> **Monitor matched albums & singles (default ON):** only the albums/singles that matched a
> liked track are monitored (not the artist's whole discography). Disable to add artists while
> leaving albums unmonitored.

> **OAuth instead of a cookie (recommended, durable & auto-refreshing):**
> 1. Create a Google Cloud OAuth client (APIs & Services → Credentials → Create
>    OAuth client ID → **Android Auto**), give it access to the **YouTube Data API**,
>    and copy the `client_id` / `client_secret`.
> 2. Put them in the sync project's `config.ini` under `[ytmusic] oauth_client_id` /
>    `oauth_client_secret` (or in the baked image's `/app/sync/config.ini`).
> 3. One time, run `python3 -m ytmusic_lidarr_sync --oauth-login` (device flow: a URL +
>    code, auto-refreshing token saved to `oauth.json`). After that the sync authenticates
>    with OAuth automatically, with no cookie to refresh.

> **Zero-touch install (baked image):** `docker/Dockerfile` builds a lidarr image with
> Python + the sync engine already inside (`/app/sync`), so anyone can add the plugin by
> installing the zip + pasting auth — **no `apk add` / file copying into the running
> container**. The default sync-project path auto-detects `/app/sync` vs
> `/config/ytmusic-lidarr-sync`. The API key + port are auto-read from Lidarr's `config.xml`.

Run once immediately from **System → Tasks → YouTube Music Sync**; the full SYNC REPORT shows
in the task's completion message (no need to open the logs).

## Why the Python bridge?

`ytmusicapi` (the YouTube Music integration) is Python-only, and faithfully
reimplementing YT Music's internal API + Lidarr ingestion in C# is a large, risky
undertaking. Shelling out to the tested CLI keeps behavior identical while still
giving you the in-app scheduling and settings surface.

## Notes / limitations

- The plugin requires the plugin-capable Lidarr branch; switching off `master` is
  one-way without a database restore.
- This scaffold follows the community plugin patterns (UniqueSingles). Exact
  provider/interface names must match your Lidarr plugin-branch build; the GitHub
  CI build is where the compiled contract is validated.
- Distributed code that references the Lidarr source carries GPL-3.0 obligations.

## Layout

```
LidarrReferences.targets          pins Lidarr reference binaries + version
scripts/prepare-lidarr.py         downloads those binaries for building
.github/workflows/build.yml       build + publish GitHub Release on main
src/Lidarr.Plugin.YoutubeMusic/
  Plugin.cs                       plugin entry (Name/Owner/GithubUrl)
  Settings/YoutubeMusicSettings.cs
  Connect/YoutubeMusicNotification.cs      settings UI (Settings → Connect)
  Tasks/YoutubeMusicSyncTask.cs            scheduled task (Settings → Metadata)
  Commands/*                              command + executor
  Services/*                              Python bridge + settings context
  Scheduling/*                            scheduled-task lifecycle service
```