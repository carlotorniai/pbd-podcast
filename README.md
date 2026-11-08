# pbd-podcast

Inbox for the daily Pharma and Biotech Daily episode. Claude produces each episode in Anthropic's cloud and stages it here. A separate private repo, which Claude cannot access, validates and publishes it to Buzzsprout.

## Layout
| Path | Purpose |
|---|---|
| `render/tts_render.py` | Offline text to speech used by the cloud job |
| `prompts/daily_task_prompt.md` | The scheduled task's instructions |
| branch `episodes` | Every script, sources list and metadata, one folder per day |
| branch `audio-inbox` | Only the next episode's files, force pushed daily |

## Schedule
| When (Europe/Zurich) | What |
|---|---|
| 05:10, Monday to Friday | Claude scheduled task builds the same day's episode and stages it on `audio-inbox` |
| 05:40 UTC, Monday to Friday (06:40 in winter, 07:40 in summer) | Private publisher validates and uploads to Buzzsprout |
| 08:00, Monday to Friday | Episode goes live on Buzzsprout, Apple, Spotify, YouTube |

## Security model
* No secrets live in this repo, and no workflow runs here.
* The publishing token sits in a separate private repo that the Claude GitHub app is not installed on.
* The publisher treats staged files as untrusted data: schema, sizes, MP3 header, duration and hashes are validated before upload. Nothing from this repo is executed there.
* The voice model download is pinned by SHA256.
