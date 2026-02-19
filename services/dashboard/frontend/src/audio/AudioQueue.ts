export enum AudioPriority {
  USER_ACTION = 0,
  ANNOUNCEMENT = 1,
  VOICE_EVENT = 2,
}

interface QueueItem {
  url: string;
  priority: AudioPriority;
}

type Listener = () => void;

const MAX_QUEUE_SIZE = 20;

class AudioQueue {
  private queue: QueueItem[] = [];
  private playing = false;
  private currentAudio: HTMLAudioElement | null = null;
  private enabled = false;
  private listeners = new Set<Listener>();

  /** Subscribe to state changes (for useSyncExternalStore). */
  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Snapshot for useSyncExternalStore. Returns the enabled flag. */
  getSnapshot = (): boolean => this.enabled;

  /** Enable or disable playback. Disabling stops current audio and clears the queue. */
  setEnabled(value: boolean) {
    this.enabled = value;
    if (!value) {
      this.stop();
      this.queue = [];
    }
    this.emit();
  }

  /** Add a URL to the queue with a given priority. */
  enqueue = (url: string, priority: AudioPriority = AudioPriority.VOICE_EVENT) => {
    if (!this.enabled) return;

    const item: QueueItem = { url, priority };

    // Insert in priority order (lower number = higher priority), FIFO within same priority
    let inserted = false;
    for (let i = 0; i < this.queue.length; i++) {
      if (this.queue[i].priority > priority) {
        this.queue.splice(i, 0, item);
        inserted = true;
        break;
      }
    }
    if (!inserted) {
      this.queue.push(item);
    }

    // Enforce max queue size — drop lowest-priority (end of queue) items
    while (this.queue.length > MAX_QUEUE_SIZE) {
      this.queue.pop();
    }

    this.emit();
    this.playNext();
  };

  /**
   * Fetch an audio URL from an API call, then enqueue it.
   * The fetcher should return the audio URL string, or null on failure.
   */
  enqueueFromApi = async (
    fetcher: () => Promise<string | null>,
    priority: AudioPriority = AudioPriority.USER_ACTION,
  ) => {
    if (!this.enabled) return;
    try {
      const url = await fetcher();
      if (url) {
        this.enqueue(url, priority);
      }
    } catch (e) {
      console.warn('AudioQueue: enqueueFromApi failed:', e);
    }
  };

  /** Clear the queue (does not stop current playback). */
  clear = () => {
    this.queue = [];
    this.emit();
  };

  private stop() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.removeAttribute('src');
      this.currentAudio = null;
    }
    this.playing = false;
  }

  private playNext = () => {
    if (this.playing || this.queue.length === 0 || !this.enabled) return;

    this.playing = true;
    const item = this.queue.shift()!;
    this.emit();

    const audio = new Audio(item.url);
    this.currentAudio = audio;

    const done = () => {
      this.currentAudio = null;
      this.playing = false;
      this.playNext();
    };

    audio.addEventListener('ended', done);
    audio.addEventListener('error', (e) => {
      console.warn('AudioQueue: playback error:', e);
      done();
    });

    audio.play().catch((e) => {
      console.warn('AudioQueue: play() rejected:', e);
      done();
    });
  };

  private emit() {
    for (const listener of this.listeners) {
      listener();
    }
  }
}

/** Singleton instance. */
export const audioQueue = new AudioQueue();
