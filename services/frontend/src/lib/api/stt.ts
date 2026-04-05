/**
 * STT Service API client.
 * Routes through nginx /api/stt/ → stt-service:8000 (separate from backend proxy).
 */

export interface TranscribeResponse {
  text: string
  cleaned_text: string
  language: string
  confidence: number
  duration_seconds: number
  provider: string
}

export interface STTProviderInfo {
  active: string
  available: string[]
  language: string
  model: string
}

const STT_BASE = '/api/stt'

/**
 * Check if the STT service is available.
 * Returns provider info or null if service is not deployed.
 */
export async function checkSTTAvailable(): Promise<STTProviderInfo | null> {
  try {
    const res = await fetch(`${STT_BASE}/providers`)
    if (!res.ok) return null
    return (await res.json()) as STTProviderInfo
  } catch {
    return null
  }
}

/**
 * Transcribe audio blob via the STT service.
 */
export async function transcribeAudio(
  audio: Blob,
  language = 'ja',
  clean = true,
): Promise<TranscribeResponse> {
  const form = new FormData()
  form.append('audio', audio, 'recording.webm')
  form.append('language', language)
  form.append('clean', String(clean))

  const res = await fetch(`${STT_BASE}/transcribe`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`STT transcription failed: ${detail}`)
  }
  return (await res.json()) as TranscribeResponse
}
