# Lidarr.Plugin.YoutubeMusic

A native Lidarr plugin (installs under **System → Plugins**) that syncs your
**YouTube Music** liked songs / playlist into Lidarr as artists + albums, and
optionally triggers album searches so Lidarr manages the FLACs.

It schedules the sync **inside Lidarr** (no external Task Scheduler needed) and
executes the proven, Python-based sync engine from this repo.

> **Headline:** plugins can hold a UI-managed schedule in-app. This plugin
> registers a scheduled task (Settings → Metadata) with a configurable
> interval, plus a settings surface under Settings → Connect.

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
                 (ytmusic-lidarr-sync Python package + its config.ini/headers.json)
```

## Prerequisites

- **Lidarr 3.1.2.4938+ on the `develop` or `nightly` branch** (the `master`
  branch does not support plugins). Verified working template target: 3.1.3.4968.
- The **ytmusic-lidarr-sync Python CLI** (this repo) installed on the Lidarr
  host, with `pip install -r requirements.txt`, a `config.ini`, and a
  `headers.json` from `python -m ytmusicapi setup`.
- **.NET 8 SDK** to build (or rely on the included GitHub Action).

## Build

Local:

```bash
cd plugin/Lidarr.Plugin.YoutubeMusic
python scripts/prepare-lidarr.py   # downloads pinned Lidarr reference binaries
dotnet build src/Lidarr.Plugin.YoutubeMusic/Lidarr.Plugin.YoutubeMusic.csproj \
    -c Release -p:PluginVersion=0.1.0
```

The output zip is `_temp/bin/Release/Lidarr.Plugin.YoutubeMusic/Lidarr.Plugin.YoutubeMusic.net8.0.zip`.
The included GitHub Action (`<repo>/.github/workflows/build.yml`) does all of the
above and attaches the zip to a GitHub **Release** on `main`.

## Install

1. Push this folder as a **public GitHub repo** named `Lidarr.Plugin.YoutubeMusic`
   (edit `Owner`/`GithubUrl` in `Plugin.cs` first).
2. In Lidarr go to **System → Plugins**, paste the repo URL, **Install**, then
   **restart Lidarr**.

## Configure

1. **Settings → Metadata → "YouTube Music Sync Scan"** — this is the entry that
   drives everything (the scheduled task). Configure it **here** (see note below
   on the auth cookie):
   - **Python executable**: `python` (or absolute path on the Lidarr host)
   - **Sync project path**: absolute path to the ytmusic-lidarr-sync project
     (must contain `config.ini` and the package)
   - **CLI arguments**: `--search` (add + trigger album searches), `--add`, or
     empty for dry-run
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

> **Monitor added albums (default ON):** the **"Monitor added albums"** checkbox on the
> entry controls whether newly added albums are auto-monitored in Lidarr (so they're
> flagged for download). Disable it to only add artists/albums without monitoring.

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
> `/config/ytmusic-lidarr-sync`. The API key is auto-read from Lidarr's `config.xml`.
3. Optionally run once immediately from **System → Tasks → YouTube Music Sync**.

The sync logs to `config/logs/Lidarr.debug.txt` (enable Debug/Trace logging in
Settings → General to see CLI stdout/stderr).

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