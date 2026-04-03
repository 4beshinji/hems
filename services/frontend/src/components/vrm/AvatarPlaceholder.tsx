import { useEffect, useRef, useState, useCallback } from 'react'
import { useAudioAnalyser } from '@/audio'
import { getMotionMeta } from '@/lib/motion-registry'

interface Props {
  className?: string
}

// Frequency band energy → mouth openness (0-1)
function computeMouthOpen(frequencyData: Uint8Array): number {
  if (frequencyData.length === 0) return 0
  // Use bins 2-20 (~340Hz-3400Hz) — speech formant range
  let sum = 0
  const start = 2, end = Math.min(20, frequencyData.length)
  for (let i = start; i < end; i++) sum += frequencyData[i]
  const avg = sum / (end - start)
  return Math.min(1, avg / 160) // normalize to 0-1
}

const TONE_EYES: Record<string, { eyeScaleY: number; browY: number }> = {
  neutral:  { eyeScaleY: 1,   browY: 0 },
  caring:   { eyeScaleY: 0.8, browY: -1 },
  humorous: { eyeScaleY: 0.7, browY: -2 },
  alert:    { eyeScaleY: 1.3, browY: -3 },
}

export default function AvatarPlaceholder({ className }: Props) {
  const { isActive, currentTone, currentMotionId, getFrequencyData } = useAudioAnalyser()
  const motionCategory = currentMotionId ? getMotionMeta(currentMotionId)?.category : null
  const [mouthOpen, setMouthOpen] = useState(0)
  const [blinkPhase, setBlinkPhase] = useState(1) // 1 = open, 0 = closed
  const rafRef = useRef<number>(0)
  const blinkTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Lip sync animation loop
  useEffect(() => {
    if (!isActive) {
      setMouthOpen(0)
      return
    }
    let prev = 0
    const tick = () => {
      const data = getFrequencyData()
      const target = computeMouthOpen(data)
      // Smooth lerp
      prev = prev + (target - prev) * 0.35
      setMouthOpen(prev)
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [isActive, getFrequencyData])

  // Blink loop
  const scheduleBlink = useCallback(() => {
    const delay = 2000 + Math.random() * 4000 // 2-6 seconds
    blinkTimerRef.current = setTimeout(() => {
      setBlinkPhase(0)
      setTimeout(() => {
        setBlinkPhase(1)
        scheduleBlink()
      }, 150)
    }, delay)
  }, [])

  useEffect(() => {
    scheduleBlink()
    return () => clearTimeout(blinkTimerRef.current)
  }, [scheduleBlink])

  const tone = currentTone || 'neutral'
  const eyes = TONE_EYES[tone] || TONE_EYES.neutral
  const isHappy = tone === 'caring' || tone === 'humorous'

  return (
    <div className={className} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', background: 'transparent' }}>
      <svg viewBox="0 0 200 280" width="100%" height="100%" style={{ maxWidth: 180, maxHeight: 260 }}>
        {/* Hair back */}
        <ellipse cx="100" cy="88" rx="62" ry="68" fill="oklch(0.35 0.05 260)" />

        {/* Neck */}
        <rect x="88" y="148" width="24" height="24" rx="4" fill="oklch(0.85 0.03 80)" />

        {/* Body / shoulders */}
        <path d="M50 172 Q50 162 65 160 L135 160 Q150 162 150 172 L155 240 Q155 250 145 250 L55 250 Q45 250 45 240 Z" fill="oklch(0.55 0.15 260)" />
        {/* Collar */}
        <path d="M80 162 L100 180 L120 162" fill="none" stroke="oklch(0.90 0.01 80)" strokeWidth="2" />

        {/* Face */}
        <ellipse cx="100" cy="100" rx="52" ry="58" fill="oklch(0.88 0.03 80)" />

        {/* Hair front */}
        <path d="M48 90 Q48 42 100 38 Q152 42 152 90 L148 72 Q140 52 100 48 Q60 52 52 72 Z" fill="oklch(0.35 0.05 260)" />
        {/* Bangs */}
        <path d="M58 78 Q65 60 80 68 Q75 55 92 62 Q90 50 108 58 Q110 48 125 60 Q130 52 140 72 L138 82 Q130 65 118 70 Q115 58 100 64 Q88 56 85 68 Q75 60 68 78 Z" fill="oklch(0.30 0.05 260)" />

        {/* Eyes */}
        <g transform={`translate(0, ${eyes.browY})`}>
          {/* Eyebrows */}
          <path d={tone === 'alert'
            ? "M68 78 Q75 72 85 76"
            : "M68 80 Q75 76 85 78"
          } fill="none" stroke="oklch(0.30 0.03 260)" strokeWidth="2" strokeLinecap="round" />
          <path d={tone === 'alert'
            ? "M115 76 Q125 72 132 78"
            : "M115 78 Q125 76 132 80"
          } fill="none" stroke="oklch(0.30 0.03 260)" strokeWidth="2" strokeLinecap="round" />
        </g>

        {/* Left eye */}
        <g transform={`translate(78, 92) scale(1, ${blinkPhase * eyes.eyeScaleY})`}>
          {isHappy ? (
            <path d="M-8 0 Q0 -8 8 0" fill="none" stroke="oklch(0.25 0.05 260)" strokeWidth="2.5" strokeLinecap="round" />
          ) : (
            <>
              <ellipse cx="0" cy="0" rx="8" ry="9" fill="white" />
              <ellipse cx="1" cy="0" rx="5" ry="6" fill="oklch(0.40 0.15 260)" />
              <ellipse cx="2" cy="-1" rx="2.5" ry="3" fill="oklch(0.15 0.05 260)" />
              <ellipse cx="4" cy="-3" rx="1.5" ry="1.5" fill="white" opacity="0.8" />
            </>
          )}
        </g>

        {/* Right eye */}
        <g transform={`translate(122, 92) scale(1, ${blinkPhase * eyes.eyeScaleY})`}>
          {isHappy ? (
            <path d="M-8 0 Q0 -8 8 0" fill="none" stroke="oklch(0.25 0.05 260)" strokeWidth="2.5" strokeLinecap="round" />
          ) : (
            <>
              <ellipse cx="0" cy="0" rx="8" ry="9" fill="white" />
              <ellipse cx="-1" cy="0" rx="5" ry="6" fill="oklch(0.40 0.15 260)" />
              <ellipse cx="0" cy="-1" rx="2.5" ry="3" fill="oklch(0.15 0.05 260)" />
              <ellipse cx="2" cy="-3" rx="1.5" ry="1.5" fill="white" opacity="0.8" />
            </>
          )}
        </g>

        {/* Nose */}
        <path d="M99 106 L97 112 Q100 114 103 112 Z" fill="oklch(0.80 0.04 60)" opacity="0.5" />

        {/* Blush (caring/humorous) */}
        {isHappy && (
          <>
            <ellipse cx="68" cy="110" rx="10" ry="5" fill="oklch(0.75 0.10 15)" opacity="0.4" />
            <ellipse cx="132" cy="110" rx="10" ry="5" fill="oklch(0.75 0.10 15)" opacity="0.4" />
          </>
        )}

        {/* Mouth — lip sync driven */}
        {mouthOpen < 0.05 ? (
          // Closed mouth — slight smile for happy tones
          <path
            d={isHappy ? "M90 122 Q100 128 110 122" : "M92 124 Q100 126 108 124"}
            fill="none"
            stroke="oklch(0.55 0.10 15)"
            strokeWidth="2"
            strokeLinecap="round"
          />
        ) : (
          // Open mouth — lip sync
          <ellipse
            cx="100"
            cy={122 + mouthOpen * 3}
            rx={5 + mouthOpen * 5}
            ry={2 + mouthOpen * 8}
            fill="oklch(0.35 0.12 15)"
          />
        )}

        {/* Ears */}
        <ellipse cx="48" cy="100" rx="6" ry="10" fill="oklch(0.85 0.04 70)" />
        <ellipse cx="152" cy="100" rx="6" ry="10" fill="oklch(0.85 0.04 70)" />

        {/* Motion-reactive arms */}
        {motionCategory === 'greeting' && (
          <g>
            {/* Right arm waving */}
            <path d="M150 180 Q170 160 175 130 Q178 120 172 118" fill="none" stroke="oklch(0.85 0.03 80)" strokeWidth="8" strokeLinecap="round">
              <animateTransform attributeName="transform" type="rotate" values="-5 150 180;10 150 180;-5 150 180" dur="0.6s" repeatCount="indefinite" />
            </path>
          </g>
        )}
        {motionCategory === 'alert' && (
          <g>
            {/* Right arm pointing */}
            <path d="M150 185 Q165 175 180 170 L190 168" fill="none" stroke="oklch(0.85 0.03 80)" strokeWidth="8" strokeLinecap="round" />
          </g>
        )}
        {motionCategory === 'emote' && (
          <g>
            {/* Both arms raised */}
            <path d="M50 185 Q35 160 30 135" fill="none" stroke="oklch(0.85 0.03 80)" strokeWidth="8" strokeLinecap="round" />
            <path d="M150 185 Q165 160 170 135" fill="none" stroke="oklch(0.85 0.03 80)" strokeWidth="8" strokeLinecap="round" />
          </g>
        )}
        {motionCategory === 'reaction' && (
          <g>
            {/* Head tilt indicator */}
            <ellipse cx="100" cy="70" rx="4" ry="4" fill="oklch(0.60 0.15 65)" opacity="0.7">
              <animate attributeName="opacity" values="0;0.7;0" dur="1.5s" repeatCount="1" />
            </ellipse>
          </g>
        )}
      </svg>
    </div>
  )
}
