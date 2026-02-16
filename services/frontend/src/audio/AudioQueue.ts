export enum AudioPriority {
  USER_ACTION = 0,
  ANNOUNCEMENT = 1,
  VOICE_EVENT = 2,
}

interface QueueItem { url: string; priority: AudioPriority }
type Listener = () => void

class AudioQueue {
  private queue: QueueItem[] = []
  private playing = false
  private currentAudio: HTMLAudioElement | null = null
  private enabled = false
  private listeners = new Set<Listener>()

  subscribe = (listener: Listener) => { this.listeners.add(listener); return () => this.listeners.delete(listener) }
  getSnapshot = () => this.enabled

  setEnabled(value: boolean) {
    this.enabled = value
    if (!value) { this.stop(); this.queue = [] }
    this.emit()
  }

  enqueue = (url: string, priority: AudioPriority = AudioPriority.VOICE_EVENT) => {
    if (!this.enabled) return
    const item = { url, priority }
    let inserted = false
    for (let i = 0; i < this.queue.length; i++) {
      if (this.queue[i].priority > priority) { this.queue.splice(i, 0, item); inserted = true; break }
    }
    if (!inserted) this.queue.push(item)
    while (this.queue.length > 20) this.queue.pop()
    this.emit()
    this.playNext()
  }

  clear = () => { this.queue = []; this.emit() }

  private stop() {
    if (this.currentAudio) { this.currentAudio.pause(); this.currentAudio = null }
    this.playing = false
  }

  private playNext = () => {
    if (this.playing || !this.queue.length || !this.enabled) return
    this.playing = true
    const item = this.queue.shift()!
    this.emit()
    const audio = new Audio(item.url)
    this.currentAudio = audio
    const done = () => { this.currentAudio = null; this.playing = false; this.playNext() }
    audio.addEventListener('ended', done)
    audio.addEventListener('error', done)
    audio.play().catch(done)
  }

  private emit() { for (const l of this.listeners) l() }
}

export const audioQueue = new AudioQueue()
