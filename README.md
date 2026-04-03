# AI Video Generate

Production-minded Python pipeline for daily short-form video generation focused on fresh, high-interest topics in Bangladesh and Japan.

## What it does

Each run:

1. discovers fresh trend candidates from RSS, Google News, optional Google Trends RSS, and optional Reddit signals
2. scores and deduplicates them per country
3. stores topic history and run state in SQLite
4. generates script, scenes, captions, SEO metadata, thumbnails, and upload payloads
5. renders a vertical MP4 using a provider-based video architecture
6. saves everything into a dated output folder

The default implementation is designed to stay usable without credentials:

- live discovery uses public feeds when reachable
- content generation falls back to a deterministic template engine
- video generation falls back to a built-in FFmpeg animated renderer

When credentials are added later, the Gemini or OpenAI content provider and future video/image adapters can be enabled without changing the pipeline shape.

## Project structure

```text
.
├── config/
├── data/
├── output/
├── prompts/
├── src/
│   └── ai_video_pipeline/
│       ├── providers/
│       │   ├── content/
│       │   └── video/
│       ├── config.py
│       ├── content.py
│       ├── logging_utils.py
│       ├── models.py
│       ├── pipeline.py
│       ├── scheduler.py
│       ├── storage.py
│       ├── thumbnail.py
│       ├── trends.py
│       ├── utils.py
│       └── video.py
├── templates/
├── tests/
├── .env.example
├── main.py
└── requirements.txt
```

## Quick start

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit [config/config.yaml](/Users/sakib/Project/AI Video Generate/config/config.yaml) and `.env` as needed.

Notes:

- `config/config.yaml` is intentionally JSON-compatible YAML so the app can still parse it even if `PyYAML` is not installed yet.
- The built-in FFmpeg animated renderer works without API credentials.
- `OPENAI_API_KEY` is now the preferred content-generation credential for this project.
- Bangladesh now defaults to Bangla output and the pipeline will attempt Bangla voiceover automatically.
- For Bangla voiceover, the project now prefers OpenAI TTS first and falls back to Gemini TTS if configured.
- `RUNWAY_API_KEY` enables the premium image-to-video provider path for cartoon animated shorts.
- `GEMINI_API_KEY` remains optional as a fallback provider.
- The included `.env.example` already has placeholders for your Gemini project metadata and API key slot.

### 3. Run now

```bash
python main.py --run-now
```

For a reproducible local demo without network access:

```bash
python main.py --run-now --sample-run
```

### 4. Run as scheduler

```bash
python main.py
```

By default the scheduler runs daily at 08:00 Asia/Tokyo time.

## Review mode

Review mode creates all research, scripts, SEO assets, and thumbnails, then stops before final video render.

Run:

```bash
python main.py --run-now --review-mode
```

Approve and render later:

```bash
python main.py --approve-date 2026-04-02
```

Review packets are written into:

- `output/YYYY-MM-DD/review_packet.json`
- `output/YYYY-MM-DD/review.html`

## Output layout

```text
output/YYYY-MM-DD/
  bangladesh/
    topic.json
    research.json
    fact_check_report.json
    script.txt
    character_sheet.json
    storyboard.json
    animation_manifest.json
    captions.srt
    title_options.txt
    final_title.txt
    description.txt
    hashtags.txt
    thumbnail_prompt.txt
    thumbnail.png
    vertical_cover.png
    scene_images/
    upload_payload_youtube.json
    upload_payload_tiktok.json
    upload_payload_instagram.json
    metadata.json
    final_video.mp4
  japan/
    ...
  run_summary.json
  review_packet.json
  review.html
  logs.txt
  logs.jsonl
```

## Provider architecture

### Content providers

- `openai`: implemented REST adapter using the OpenAI Responses API, current default
- `gemini`: implemented REST adapter using `generateContent`, fallback option
- `template`: built-in deterministic generator, no credentials required

### Voiceover providers

- `openai_tts`: implemented REST adapter using the OpenAI speech API, current default
- `gemini_tts`: implemented REST adapter using Gemini TTS preview, fallback option
- `piper_tts`: local offline TTS adapter for Piper when binary and voice models are installed
- `noop`: safe fallback when no key is configured

### Video providers

- `runway`: implemented REST adapter for `POST /v1/image_to_video` plus `GET /v1/tasks/{id}` polling, using the storyboard and seed images to generate per-scene clips
- `slideshow`: fully implemented FFmpeg fallback that renders a finished short-form MP4
- `sora`, `kling`, `pika`: adapter stubs isolated behind a common interface and ready for credential-specific implementation

The pipeline always prioritizes a finished deliverable. If OpenAI or another premium provider is unavailable or fails, it falls back to Gemini or `template` for content and the animated fallback renderer for video.

When `OPENAI_API_KEY` is available, the pipeline also attempts to generate per-scene still images with the OpenAI image API and animates those images in the final vertical video before falling back to abstract motion scenes.

When `RUNWAY_API_KEY` is available, the pipeline prefers Runway for scene-level image-to-video generation. It uses the generated scene images first, then character sheets, then a local placeholder seed frame if no image provider is available.

If voiceover generation fails or no provider key is configured, the video still renders and the run is logged with a warning instead of failing outright.

For proper offline voiced output, install Piper locally and configure `PIPER_MODEL_EN`, `PIPER_MODEL_JA`, and/or `PIPER_MODEL_BN` in `.env`. The pipeline will automatically prefer OpenAI and Gemini first, then fall back to Piper when available.

## Safety and credibility

The pipeline:

- stores source URLs and citations
- stores a pre-script fact-check report for the selected topic
- flags sensitive, political, graphic, and misinformation-adjacent topics
- penalizes risky topics during selection
- prefers candidates with multiple trusted sources
- skips recently used topics within a cooldown window
- marks weakly sourced topics as `fact_check_status = "needs_review"`

This is intentionally conservative. It is built to reduce low-quality spam behavior, not maximize output volume.

## Scheduling options

### Built-in scheduler

`python main.py`

### Cron example

```cron
0 8 * * * cd /Users/sakib/Project/AI\ Video\ Generate && /opt/homebrew/bin/python3 main.py --run-now >> cron.log 2>&1
```

### systemd user service

Create a user timer that invokes `python main.py --run-now`.

### Docker

Docker is not included in this first version, but the app is structured so it can be containerized cleanly later.

## Tests

```bash
python -m unittest discover -s tests -v
```

Covered in the first version:

- trend scoring behavior
- duplicate/history filtering
- cartoon storyboard generation structure

## Configuration highlights

The default run is already set to two videos per day total:

- 1 for Bangladesh
- 1 for Japan

You can change:

- countries and enabled status
- language per country
- script duration
- tone
- providers
- review or auto mode
- daily schedule
- number of videos per country
- history cooldown window
- thumbnail style
- background music and voiceover flags

## Provider checks

Validate Gemini content and TTS access without starting a full run:

```bash
python main.py --check-providers
```

This is the fastest way to confirm your configured content and voice providers work before the daily scheduler starts.

## Missing credentials and extension points

The following remain adapter-driven and credential-dependent:

- OpenAI content/image/voice generation
- Runway/Kling/Pika/Sora generation
- social APIs with authenticated access
- platform auto-upload

## Security note

Never commit `.env` or paste an exposed API key into the repository history. This project now ignores `.env`, `output/`, and local SQLite databases via [`.gitignore`](/Users/sakib/Project/AI Video Generate/.gitignore).

These are already isolated in provider modules and documented in code so they can be filled in without restructuring the system.
