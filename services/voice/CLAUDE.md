# services/voice/ (+ services/stt/)

Audio I/O stack: plugin-based TTS (voice-service) and plugin-based STT (stt-service). Extends parent `hems/CLAUDE.md`.

## Voice Service (Plugin-based TTS)

TTSProvider ABC with backends (registry: `provider_factory._PROVIDERS`):
- `voisona` — VoiSona Talk (host app, default)
- `voicevox` — VOICEVOX Docker (profile: voicevox, default fallback)
- `espeak` — espeak-ng (no GPU)
- `edge-tts` — Microsoft Edge TTS (cloud, free)
- `aivoice` — A.I.VOICE Editor (Wine/Windows host, VOICEVOX 互換 HTTP API)

FallbackProvider: `TTS_FALLBACK` env var or character YAML `voice.fallback` で自動切替。
Primary 失敗時に fallback へ委譲、復帰時に自動復帰。

## STT Service (Plugin-based Speech-to-Text)

Self-hosted speech recognition with query cleaning. Replaces browser Web Speech API.

- **stt-service**: Docker service (Python/FastAPI) with plugin-based STT providers
  - Plugin system mirrors voice-service TTS architecture (STTProvider ABC)
  - Providers: `whisper` (faster-whisper, default), `sherpa-onnx` (Parakeet 0.6B JP), `qwen3-asr` (Qwen3-ASR 1.7B)
  - Query cleaner: regex-based filler removal + optional LLM rewrite via Ollama
  - Audio format conversion: WebM/Opus/MP3/WAV → 16kHz mono WAV (ffmpeg)
  - REST API: `POST /api/stt/transcribe` (multipart), `GET /api/stt/providers`
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
STT_LLM_REWRITE=false     # enable LLM query cleaning (requires Ollama)
HEMS_PORT_STT=8023
```

ROCm (AMD GPU) usage:
```bash
# gpu_setup.py generates docker-compose.gpu.yml with ROCm devices + build args
python infra/scripts/gpu_setup.py
cd infra && docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  --profile stt up -d --build
# GPU_TYPE=rocm build arg → PyTorch ROCm installed in image
# /dev/kfd auto-detected at runtime → transformers backend selected
```
