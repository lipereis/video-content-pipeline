# video-content-pipeline

Drop a video in a folder and get back a transcript, five opening hooks, a shot-by-shot script and captions for Instagram and LinkedIn, as a Markdown file ready to review. An n8n workflow runs the steps; everything runs on your machine, with no API key.

I edit short-form video for a living. Writing the hooks and captions for each clip was the part I kept postponing, so I automated the first draft.

```
data/inbox/clip.mp4
      │
      ▼
┌──────────────── n8n workflow (every minute) ────────────────┐
│  Reserve new videos → Transcribe → Generate → Archive       │
│                            │            │                   │
│                            └── on error ┴──→ Archive failed │
└──────────────────────────────────────────────────────────────┘
      │ HTTP                │                     │
      ▼                     ▼                     ▼
   worker (FastAPI)     ffmpeg + Whisper     Metis + local LLM (Ollama)

data/saida/clip.md              hooks, script, captions
data/saida/clip.transcricao.txt transcript
data/processados/clip.mp4       the video, once done
data/falhou/clip.mp4(.erro.txt) the video and the reason, if a step failed
```

## How it works

- **n8n** only orchestrates. The workflow is seven nodes and lives in [`workflow/video-content-pipeline.json`](workflow/video-content-pipeline.json), so it is versioned with the code.
- **worker** is a small FastAPI service with one endpoint per workflow step: `/claim`, `/transcribe`, `/generate`, `/archive`. Keeping the logic out of n8n is what makes it testable.
- **Transcription** uses ffmpeg to pull the audio and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) to transcribe it on CPU.
- **Generation** uses [Metis](https://github.com/lipereis/metis-content-strategist), my content-strategy agent, pinned to a commit. Metis validates every model reply against a Pydantic schema and sends the error back to the model when it fails.
- **LLM** is any OpenAI-compatible endpoint. The default is [Ollama](https://ollama.com) on the host.

Two details that took some thought:

- **A video is never processed twice.** `/claim` moves a file from `inbox/` to `processando/` before returning it, so the next poll cannot see it. Files still being copied are skipped until they have been untouched for 10 seconds.
- **Failures are kept, not lost.** If transcription or generation fails, the workflow's error branch moves the video to `falhou/` and writes the reason next to it. A silent video is rejected at transcription instead of generating text from nothing.

## Run it

You need Docker and Ollama with a model pulled (`ollama pull qwen2.5:7b`).

```bash
docker compose up -d --build
docker compose exec n8n n8n import:workflow --input=/workflow/video-content-pipeline.json
docker compose exec n8n n8n publish:workflow --id=videoContentPipeline
docker compose restart n8n
```

Then copy a video into `data/inbox/`. Within a minute or two the result appears in `data/saida/`. The n8n editor is at http://localhost:5678 if you want to watch the executions.

Settings, as environment variables or in a `.env` file:

| Variable | Default | What it does |
|---|---|---|
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL` | `qwen2.5:7b` | Model name |
| `LLM_API_KEY` | `ollama` | Key for hosted endpoints |
| `LLM_TIMEOUT` | `600` | Seconds per LLM request |
| `WHISPER_MODEL` | `small` | faster-whisper model size |
| `TONE` | `creator` | Tone file in [`tone/`](tone), without `.yaml` |

## Tests

```bash
cd worker
pip install -r requirements-dev.txt
METIS_PATH=/path/to/metis-content-strategist pytest tests -q
```

Six tests cover the folder state machine and the HTTP endpoints, including the failure and path-traversal cases. Whisper and the LLM are replaced by fakes, so the tests need no model, GPU or network. CI runs them on every push.

## What I measured

On my machine (RTX 2060 6 GB, Whisper on CPU, qwen2.5:7b on Ollama), with n8n 2.42.5:

- A 24-second clip and a 3-minute clip both went from `inbox/` to `processados/` through the scheduled workflow.
- The error branch works: two real failures during development (an audio-decoding bug and an LLM timeout) both landed in `falhou/` with the reason written out.
- The first LLM call after Ollama starts took about 110 seconds just to load the model, which is why the timeout defaults to 600.

## Limits

- **The output is a first draft, not a finished post.** With a 7B local model the Portuguese is sometimes clumsy, and it does not always follow the tone file (it added emoji when told not to).
- **It only works when the video says something.** On the 3-minute clip, an interview with facts and numbers, every number in the output came from the transcript. On the 24-second clip, casual vlog chatter with no real content, the model ignored the instruction to use only the source and invented sales statistics. Review before posting.
- I have run it on two videos, both in English. Portuguese audio is untested.
- Videos are processed one batch at a time and transcription is CPU-only, so long videos are slow.
- It does not post anywhere. That is deliberate: a person should read the draft first.
- Tested only on Windows with Docker Desktop.

Built with AI assistance (Claude Code); the design, the testing and the decisions on what to keep are mine.
