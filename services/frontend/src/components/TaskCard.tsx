import { useState } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, Clock, MapPin, Zap } from 'lucide-react'
import { AudioPriority } from '../audio'

const API_BASE = '/api'

const URGENCY_COLORS: Record<number, string> = {
  0: 'bg-gray-100 text-gray-600',
  1: 'bg-blue-100 text-blue-700',
  2: 'bg-green-100 text-green-700',
  3: 'bg-orange-100 text-orange-700',
  4: 'bg-red-100 text-red-700',
}

const URGENCY_LABELS: Record<number, string> = {
  0: '延期可', 1: '低', 2: '通常', 3: '高', 4: '緊急',
}

interface Props {
  task: {
    id: number
    title: string
    description?: string
    location?: string
    xp_reward: number
    urgency: number
    zone?: string
    task_type?: string[]
    estimated_duration?: number
    completion_audio_url?: string
    assigned_to?: number | null
    report_status?: string | null
  }
  onComplete: () => void
  enqueueAudio: (url: string, priority: AudioPriority) => void
  audioEnabled: boolean
}

export default function TaskCard({ task, onComplete, enqueueAudio, audioEnabled }: Props) {
  const [completing, setCompleting] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [reportStatus, setReportStatus] = useState('no_issue')
  const [completionNote, setCompletionNote] = useState('')

  const handleComplete = async () => {
    setCompleting(true)
    try {
      const resp = await fetch(`${API_BASE}/tasks/${task.id}/complete`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_status: reportStatus, completion_note: completionNote }),
      })
      if (resp.ok) {
        if (audioEnabled && task.completion_audio_url) {
          enqueueAudio(task.completion_audio_url, AudioPriority.USER_ACTION)
        }
        onComplete()
      }
    } catch {
    } finally {
      setCompleting(false)
      setShowReport(false)
    }
  }

  return (
    <motion.div
      className="bg-white rounded-xl elevation-2 p-5 flex flex-col gap-3"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
    >
      <div className="flex items-start justify-between">
        <h3 className="font-semibold text-gray-900 text-lg leading-tight">{task.title}</h3>
        <span className={`text-xs px-2 py-1 rounded-full font-medium ${URGENCY_COLORS[task.urgency] || URGENCY_COLORS[2]}`}>
          {URGENCY_LABELS[task.urgency] || '通常'}
        </span>
      </div>

      {task.description && (
        <p className="text-sm text-gray-600 line-clamp-2">{task.description}</p>
      )}

      <div className="flex flex-wrap gap-2 text-xs text-gray-500">
        {task.zone && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3 h-3" />{task.zone}
          </span>
        )}
        {task.location && <span>{task.location}</span>}
        {task.estimated_duration && (
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />{task.estimated_duration}min
          </span>
        )}
      </div>

      <div className="flex items-center justify-between mt-auto pt-2 border-t border-gray-100">
        <span className="flex items-center gap-1 text-purple-600 font-bold">
          <Zap className="w-4 h-4" />{task.xp_reward} XP
        </span>

        {!showReport ? (
          <button
            onClick={() => setShowReport(true)}
            className="px-4 py-2 bg-green-500 text-white rounded-lg text-sm font-medium hover:bg-green-600 transition-colors"
          >
            Complete
          </button>
        ) : (
          <div className="flex flex-col gap-2 w-full mt-2">
            <select
              value={reportStatus}
              onChange={e => setReportStatus(e.target.value)}
              className="text-sm border rounded px-2 py-1"
            >
              <option value="no_issue">問題なし</option>
              <option value="resolved">解決済み</option>
              <option value="needs_followup">フォローアップ必要</option>
              <option value="cannot_resolve">解決不可</option>
            </select>
            <textarea
              value={completionNote}
              onChange={e => setCompletionNote(e.target.value)}
              placeholder="メモ (任意)"
              className="text-sm border rounded px-2 py-1 resize-none"
              rows={2}
              maxLength={500}
            />
            <div className="flex gap-2">
              <button
                onClick={handleComplete}
                disabled={completing}
                className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-green-500 text-white rounded-lg text-sm hover:bg-green-600 disabled:opacity-50"
              >
                <CheckCircle className="w-4 h-4" />
                {completing ? '...' : '完了'}
              </button>
              <button
                onClick={() => setShowReport(false)}
                className="px-3 py-2 bg-gray-200 rounded-lg text-sm hover:bg-gray-300"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  )
}
