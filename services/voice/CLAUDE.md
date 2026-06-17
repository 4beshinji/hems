# services/voice/ (+ services/stt/)

Audio I/O stack: plugin-based TTS (voice-service) and plugin-based STT (stt-service). Extends parent `hems/CLAUDE.md`.

## Voice Service (Plugin-based TTS)

TTSProvider ABC with backends (registry: `provider_factory._PROVIDERS`):

- `voicevox` — VOICEVOX Docker (profile: voicevox)
- `espeak` — espeak-ng (no GPU, always available)
- `edge-tts` — Microsoft Edge TTS (cloud, free)
- `voisona` — VoiSona Talk (host app)
- `aivoice` — A.I.VOICE Editor (Wine/Windows host, VOICEVOX-compatible HTTP API)

`style-bert-vits2` is **not implemented** as a TTS provider. Selecting it falls back to `espeak`.

### Defaults (distinguished by source)

The effective value depends on where it is set:

| Setting | Code default | `env.example` template | `docker-compose.yml` fallback |
|---|---|---|---|
| `TTS_PROVIDER` | `voicevox` (`provider_factory.py`) | `voisona` | `espeak` |
| `TTS_FALLBACK` | (none) | `voicevox` | (none) |
| `LLM_API_URL` (speech gen) | `http://mock-llm:8000/v1` | `http://ollama:11434/v1` | `http://ollama:11434/v1` |
| `LLM_MODEL` (speech gen) | `gpt-4o-mini` | `gemma4:e4b-it-q8_0` | `gpt-oss:20b` |

Code defaults apply when the env var is absent and no character YAML override exists. Docker Compose fallbacks apply when the variable is not set in `.env`. `env.example` shows one recommended production/dev template, not a runtime default.

**Note:** `speech_generator.py` has its own code defaults (`mock-llm:8000/v1`, `gpt-4o-mini`) that differ from the `docker-compose.yml` voice-service fallback (`ollama:11434/v1`, `gpt-oss:20b`). In the container the Compose/env values take precedence; the hardcoded defaults are mainly for local unit testing.

### Fallback provider

`TTS_FALLBACK` env var or character YAML `voice.fallback` enables automatic failover. Primary failures are delegated to the fallback; service automatically returns to primary when it recovers.

### Internal authentication

All `/api/voice/*` mutation endpoints require `Authorization: Bearer <HEMS_INTERNAL_TOKEN>` when `HEMS_INTERNAL_TOKEN` is non-empty. `GET /api/voice/health` and `GET /audio/{filename}` are unauthenticated. If `HEMS_INTERNAL_TOKEN` is empty, auth checks are skipped (dev/zero-config).

### Text preprocessing

Incoming text is run through `TextProcessor` before synthesis:

- Unicode NFKC normalization
- Markdown stripping (`***bold***`, `# headers`)
- Punctuation normalization (`...` → `…`, repeated `。`, em-dash unification)
- Whitespace collapse

Applied to `POST /api/voice/synthesize` and each item in `POST /api/voice/batch-synthesize`.

### Passive health monitoring

Providers can opt into background health polling by setting `health_poll_interval` and implementing `passive_health_snapshot()`. `main.py` runs a vendor-agnostic loop; currently `voisona` uses this to surface host-app health. Results are exposed on `GET /api/voice/health`.

### REST API

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | no | Service name and active provider |
| GET | `/api/voice/health` | no | Service + TTS health snapshot |
| POST | `/api/voice/synthesize` | Bearer | Synthesize arbitrary text |
| POST | `/api/voice/announce` | Bearer | Generate + speak task text |
| POST | `/api/voice/announce_with_completion` | Bearer | Generate announcement + completion pair |
| POST | `/api/voice/feedback/{feedback_type}` | Bearer | Feedback utterance |
| POST | `/api/voice/batch-synthesize` | Bearer | Parallel batch synthesis |
| GET | `/audio/{filename}` | no | Serve generated MP3 |

`POST /api/voice/batch-synthesize` accepts a `prefix` and list of `{clip_id, text, tone?}`. Output filename is `{prefix}_{clip_id}.mp3`; re-running with the same prefix overwrites files, enabling cheap boot-load regeneration. `prefix` and `clip_id` must match `^[A-Za-z0-9._-]+$`.

## STT Service (Plugin-based Speech-to-Text)

Self-hosted speech recognition with query cleaning. Replaces browser Web Speech API.

- **stt-service**: Docker service (Python/FastAPI) with plugin-based STT providers
  - Plugin system mirrors voice-service TTS architecture (`STTProvider` ABC)
  - Providers: `whisper` (faster-whisper, default), `sherpa-onnx` (Parakeet 0.6B JP), `qwen3-asr` (Qwen3-ASR 1.7B)
  - Query cleaner: regex-based filler removal + optional LLM rewrite via Ollama
  - Audio format conversion: WebM/Opus/MP3/WAV → 16kHz mono WAV (ffmpeg)
  - REST API: `POST /api/stt/transcribe` (multipart, auth), `GET /api/stt/providers` (auth), `GET /health` (unauthenticated)
- **Frontend**: Push-to-talk + VAD auto mode (Silero VAD ONNX via `@ricky0123/vad-web`)
  - Push-to-talk: click mic → record → click again → transcribe
  - Auto (VAD): continuous speech detection → auto-transcribe → auto-send
  - Mode toggle: PTT / VAD / OFF (cycles with button)
  - Falls back to Web Speech API when STT service unavailable
- **Profile**: `docker compose --profile stt up -d --build`
- **Privacy**: All processing local, no audio stored
- **GPU**: Auto-detect — CUDA uses faster-whisper (CTranslate2), ROCm uses transformers + PyTorch ROCm, CPU uses faster-whisper int8

| Provider | Model | Languages | VRAM | Best for |
|----------|-------|-----------|------|----------|
| `whisper` | large-v3-turbo | 99 | ~1.5GB | General use (default) |
| `sherpa-onnx` | Parakeet 0.6B JP | ja | ~0.6GB | Japanese speed |
| `qwen3-asr` | Qwen3-ASR 1.7B | 52 | ~3.5GB | Best quality |

Configure in `.env`:

```bash
STT_PROVIDER=whisper
STT_MODEL=large-v3-turbo
STT_LANGUAGE=ja
STT_DEVICE=auto           # auto, cpu, cuda, rocm
STT_COMPUTE_TYPE=auto     # auto, float16, int8
STT_BEAM_SIZE=5           # beam search width (whisper)
STT_MAX_AUDIO_SECONDS=60  # hard upload length cap
STT_LLM_REWRITE=false     # enable LLM query cleaning (requires Ollama)
STT_LLM_MODEL=            # override model for rewrite; empty falls back to LLM_MODEL
HEMS_INTERNAL_TOKEN=      # gates /api/stt/*; empty disables auth
HEMS_PORT_STT=8023
```

`STT_LLM_MODEL` defaults to the value of `LLM_MODEL` when empty. `LLM_API_URL` is also used by the query cleaner.

ROCm (AMD GPU) usage:

```bash
# gpu_setup.py generates docker-compose.gpu.yml with ROCm devices + build args
python infra/scripts/gpu_setup.py
cd infra && docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  --profile stt up -d --build
# GPU_TYPE=rocm build arg → PyTorch ROCm installed in image
# /dev/kfd auto-detected at runtime → transformers backend selected
```
