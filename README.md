# AI Video Generate

Production-oriented Python pipeline for generating daily short-form videos from trend signals, with support for Bangladesh and Japan outputs.

## What This Project Does

Each run can:

1. Discover trending candidates from public sources
2. Score and deduplicate topics per country
3. Build script + scene plans + captions + metadata
4. Render a vertical short video (with fallback mode)
5. Save all artifacts in a dated output directory

The system is designed to degrade gracefully:

- No API key: template content + FFmpeg fallback rendering
- API keys available: OpenAI/Gemini content and richer media paths

## Tech Highlights

- Provider-based architecture (content, TTS, video)
- Review-first mode for safer publish workflow
- SQLite state/history tracking
- Test coverage for trend scoring and selection logic
- Scheduler support for unattended daily runs

## Project Structure

```text
.
├── config/
├── data/
├── prompts/
├── src/ai_video_pipeline/
├── templates/
├── tests/
├── main.py
└── requirements.txt
```

## Quick Start

```bash
git clone https://github.com/sakib-maho/ai-video-generate.git
cd ai-video-generate
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update:

- `config/config.yaml`
- `.env`

Then run once:

```bash
python main.py --run-now
```

Offline/sample run:

```bash
python main.py --run-now --sample-run
```

Single country run:

```bash
python main.py --run-now --country bangladesh
```

## Scheduler

Start scheduler mode:

```bash
python main.py
```

Default schedule is daily at 08:00 (Asia/Tokyo).

## Review Mode

Generate planning artifacts first, render later:

```bash
python main.py --run-now --review-mode
python main.py --approve-date 2026-04-02
```

Review artifacts are written to `output/YYYY-MM-DD/`.

## Provider Model

Content providers:

- `openai`
- `gemini`
- `template` fallback

Voice providers:

- `openai_tts`
- `gemini_tts`
- `piper_tts`
- `noop` fallback

Video providers:

- `runway`
- `slideshow` (FFmpeg fallback)
- adapter stubs for future integrations

## Safety and Quality Controls

- Topic source storage and citation tracking
- Fact-check report generation
- Risk-aware topic scoring
- Duplicate/recent topic avoidance
- Conservative fallback behavior to ensure deliverables

## Testing

```bash
python -m unittest discover -s tests -v
```

## Security

- Never commit `.env`
- Keep API keys in local environment variables only
- Output and local DB artifacts are ignored via `.gitignore`

## License

MIT (see `LICENSE` if present).
