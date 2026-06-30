import { memo } from 'react'
import { ThumbsUp, ThumbsDown, RotateCcw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSubmitFeedback } from '@/hooks/mutations/use-feedback'
import type { FeedbackTargetType, FeedbackType } from '@/lib/types'

interface Props {
  targetType: FeedbackTargetType
  targetId: string
  size?: 'sm' | 'xs'
  showCancel?: boolean
  showRerun?: boolean
}

const SIZE_CLASS = {
  sm: 'h-7 w-7',
  xs: 'h-6 w-6',
}

const ICON_SIZE = {
  sm: 'h-3.5 w-3.5',
  xs: 'h-3 w-3',
}

export const FeedbackButtons = memo(function FeedbackButtons({
  targetType,
  targetId,
  size = 'xs',
  showCancel = false,
  showRerun = false,
}: Props) {
  const mutation = useSubmitFeedback()

  const send = (feedbackType: FeedbackType) => {
    mutation.mutate({
      target_type: targetType,
      target_id: targetId,
      feedback_type: feedbackType,
      channel: 'frontend',
    })
  }

  return (
    <div className="inline-flex items-center gap-1">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={SIZE_CLASS[size]}
        aria-label="良い"
        onClick={() => send('explicit_up')}
        disabled={mutation.isPending}
      >
        <ThumbsUp className={ICON_SIZE[size]} />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={SIZE_CLASS[size]}
        aria-label="悪い"
        onClick={() => send('explicit_down')}
        disabled={mutation.isPending}
      >
        <ThumbsDown className={ICON_SIZE[size]} />
      </Button>
      {showCancel && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={SIZE_CLASS[size]}
          aria-label="取り消し"
          onClick={() => send('cancel')}
          disabled={mutation.isPending}
        >
          <X className={ICON_SIZE[size]} />
        </Button>
      )}
      {showRerun && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={SIZE_CLASS[size]}
          aria-label="再実行"
          onClick={() => send('rerun')}
          disabled={mutation.isPending}
        >
          <RotateCcw className={ICON_SIZE[size]} />
        </Button>
      )}
    </div>
  )
})
