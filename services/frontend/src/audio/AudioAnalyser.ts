type Listener = () => void

class AudioAnalyser {
  private ctx: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private frequencyData = new Uint8Array(0) as Uint8Array<ArrayBuffer>
  private _isActive = false
  private _currentTone: string | null = null
  private _currentMotionId: string | null = null
  private listeners = new Set<Listener>()

  subscribe = (listener: Listener) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  getSnapshot = () => ({ isActive: this._isActive, currentTone: this._currentTone, currentMotionId: this._currentMotionId })

  private ensureContext() {
    if (this.ctx) return
    this.ctx = new AudioContext()
    this.analyser = this.ctx.createAnalyser()
    this.analyser.fftSize = 256
    this.analyser.smoothingTimeConstant = 0.8
    this.analyser.connect(this.ctx.destination)
    this.frequencyData = new Uint8Array(this.analyser.frequencyBinCount) as Uint8Array<ArrayBuffer>
  }

  connectSource(audio: HTMLAudioElement, tone?: string, motionId?: string) {
    this.ensureContext()
    try {
      const source = this.ctx!.createMediaElementSource(audio)
      source.connect(this.analyser!)
      this._isActive = true
      this._currentTone = tone ?? null
      this._currentMotionId = motionId ?? null
      this.emit()

      const onEnd = () => {
        this._isActive = false
        this._currentTone = null
        this._currentMotionId = null
        this.emit()
        audio.removeEventListener('ended', onEnd)
        audio.removeEventListener('error', onEnd)
        audio.removeEventListener('pause', onEnd)
      }
      audio.addEventListener('ended', onEnd)
      audio.addEventListener('error', onEnd)
      audio.addEventListener('pause', onEnd)
    } catch {
      // MediaElementAudioSourceNode already created for this element — skip
    }
  }

  getFrequencyData(): Uint8Array<ArrayBuffer> {
    if (this.analyser && this._isActive) {
      this.analyser.getByteFrequencyData(this.frequencyData)
    }
    return this.frequencyData
  }

  get isActive() { return this._isActive }
  get currentTone() { return this._currentTone }

  /** 開発用: トーンを直接セットしてサブスクライバーに通知する */
  setTestTone(tone: string | null, durationMs = 5000) {
    this._isActive = tone !== null
    this._currentTone = tone
    this.emit()
    if (tone !== null && durationMs > 0) {
      setTimeout(() => {
        this._isActive = false
        this._currentTone = null
        this.emit()
      }, durationMs)
    }
  }

  /** 開発用: モーションIDを直接セットしてアバターに再生させる */
  setTestMotion(motionId: string | null) {
    // useMotionPlayer は前回値と異なる場合のみ再生するため、一度 null を経由
    this._currentMotionId = null
    this.emit()
    if (motionId) {
      setTimeout(() => {
        this._currentMotionId = motionId
        this.emit()
      }, 30)
    }
  }

  private emit() { for (const l of this.listeners) l() }
}

export const audioAnalyser = new AudioAnalyser()
