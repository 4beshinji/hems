export interface MotionMeta {
  file: string
  duration: number
  category: string
}

const MOTION_REGISTRY: Record<string, MotionMeta> = {
  // VRoid official motion pack (pixiv)
  greeting_wave:   { file: '/models/motions/greeting_wave.vrma',   duration: 3.0, category: 'greeting' },
  celebrate:       { file: '/models/motions/celebrate.vrma',       duration: 4.0, category: 'emote' },
  point_alert:     { file: '/models/motions/point_alert.vrma',     duration: 3.5, category: 'alert' },
  stretch_suggest: { file: '/models/motions/stretch_suggest.vrma', duration: 4.0, category: 'gesture' },
  show_full:       { file: '/models/motions/show_full.vrma',       duration: 4.0, category: 'gesture' },
  spin:            { file: '/models/motions/spin.vrma',            duration: 3.0, category: 'emote' },
  model_pose:      { file: '/models/motions/model_pose.vrma',      duration: 3.0, category: 'gesture' },
  // tk256ailab/vrm-viewer (MIT)
  thinking_pose:   { file: '/models/motions/thinking_pose.vrma',   duration: 2.0, category: 'gesture' },
  wave_goodbye:    { file: '/models/motions/wave_goodbye.vrma',    duration: 2.5, category: 'greeting' },
  surprise_react:  { file: '/models/motions/surprise_react.vrma',  duration: 1.5, category: 'reaction' },
  nod_agree:       { file: '/models/motions/nod_agree.vrma',       duration: 1.5, category: 'reaction' },
  bow_polite:      { file: '/models/motions/bow_polite.vrma',      duration: 2.0, category: 'greeting' },
  shrug_confused:  { file: '/models/motions/shrug_confused.vrma',  duration: 1.8, category: 'reaction' },
  look_around:     { file: '/models/motions/look_around.vrma',     duration: 2.5, category: 'idle' },
  relax:           { file: '/models/motions/relax.vrma',           duration: 2.5, category: 'idle' },
  sleepy:          { file: '/models/motions/sleepy.vrma',          duration: 2.0, category: 'idle' },
}

export function getMotionMeta(motionId: string): MotionMeta | null {
  return MOTION_REGISTRY[motionId] ?? null
}
