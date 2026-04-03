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

  private emit() { for (const l of this.listeners) l() }
}

export const audioAnalyser = new AudioAnalyser()
