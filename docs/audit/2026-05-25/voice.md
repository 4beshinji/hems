# 監査: voice (incl. stt) — 2026-05-25

## スコープ
- 対象 path:
  - `services/voice/src/`: `main.py`(323)・`models.py`(61)・`tts_provider.py`(33)・`provider_factory.py`(82)・
    `text_processor.py`(44)・`speech_generator.py`(91)・`providers/`(voicevox 78 / voisona 279 / espeak 58 /
    edge_tts 49 / aivoice 98 / fallback 38)
  - `services/stt/src/`: `main.py`(147)・`models.py`(26)・`audio_utils.py`(98)・`stt_provider.py`(40)・
    `query_cleaner.py`(139)・`provider_factory.py`(66)・`providers/`(whisper 240 / sherpa_onnx 111 / qwen3_asr 147)
  - 計 ~2,250 LOC
- 参照 canonical doc: `services/voice/CLAUDE.md`(stt 含む)

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | voice/CLAUDE.md が TTS backend を 4 件(voisona/voicevox/espeak/edge-tts)列挙 | `provider_factory._PROVIDERS` は **5 件**(+`aivoice` = A.I.VOICE, Wine/Windows host, VOICEVOX 互換 API) | services/voice/CLAUDE.md | ✅ aivoice 追記 |
| 2 | root `CLAUDE.md` 比較表「5 backends: ... / **style-bert-vits2**」 | 5 番目の実体は `aivoice`。`style-bert-vits2` は repo 全体で root CLAUDE.md にしか出現しないゴースト名 | CLAUDE.md(Key Differences 表) | ✅ aivoice に訂正 |

検証 OK(乖離なし):
- STT provider: whisper / sherpa-onnx / qwen3-asr の 3 件 = `stt/provider_factory.py` と一致。REST API(`POST /api/stt/transcribe` / `GET /api/stt/providers`)も一致。
- FallbackProvider(TTS_FALLBACK / character YAML voice.fallback)= `provider_factory.create_provider` の wrap 実装と一致。

## 命名所見(refactor-ready)
- 特筆なし。provider 名・クラス名は明快。

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | `SpeechGenerator._call_llm` が呼び出し毎に新規 `aiohttp.ClientSession` を生成 | voice/src/speech_generator.py:78 | app lifespan で共有 session を持たせる(voice-service は brain ほど高頻度でないため優先度低) |
| P2 | voice-service が独自に OpenAI 互換 LLM 呼び出しを実装(brain の `llm_client` と別実装) | voice/src/speech_generator.py:73-91 | 別プロセスのため共有不可。重複は許容だが、将来 LLM 呼び出し仕様変更時に 2 箇所メンテ要 |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | voice/main.py に VoiSona 専用 health loop(`_voisona_health_loop` / `_get_voisona_provider`)が混在 — default provider 固有ロジックが汎用 main に侵入 | voice/src/main.py:75-140 | provider 側の health hook に委譲できると汎用性向上(優先度低) |

## 後続リファクタ推奨(優先度順サマリ)
- **P2**: `_call_llm` の共有 session 化、VoiSona 専用 health ロジックの provider 側委譲。
- **P0/P1**: 無し。TTS/STT とも plugin(ABC + factory)構成が明快で、各 provider の責務が独立。find-replace 事故・dead code 無し。voice-service は `_check_auth`(Header ベース)で認証あり(backend の no-op とは対照的)。**クリーンなユニット**。
