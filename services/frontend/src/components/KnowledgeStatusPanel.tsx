import { BookOpen, FileText, RefreshCw } from 'lucide-react'
import type { KnowledgeData } from '../App'

interface Props {
  knowledge: KnowledgeData | null
}

export default function KnowledgeStatusPanel({ knowledge }: Props) {
  if (!knowledge || knowledge.status === 'no_data') return null

  return (
    <div className="bg-white rounded-xl elevation-2 p-5 mt-4">
      <h3 className="font-semibold text-gray-800 flex items-center gap-2 mb-3">
        <BookOpen className="w-5 h-5 text-amber-500" />
        Knowledge Base
      </h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-50">
          <FileText className="w-4 h-4 text-amber-500 flex-shrink-0" />
          <div>
            <span className="text-sm font-medium text-gray-700">
              {knowledge.total_notes} ノート
            </span>
            <p className="text-xs text-gray-500">
              {knowledge.indexed} indexed
            </p>
          </div>
        </div>
        {knowledge.recent_changes && knowledge.recent_changes.length > 0 && (
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-50 sm:col-span-2">
            <RefreshCw className="w-4 h-4 text-blue-500 flex-shrink-0" />
            <div className="min-w-0">
              <span className="text-sm font-medium text-gray-700">最近の変更</span>
              <div className="space-y-0.5">
                {knowledge.recent_changes.slice(-3).reverse().map((change, i) => (
                  <p key={i} className="text-xs text-gray-500 truncate">
                    {change.title} ({change.action})
                  </p>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
