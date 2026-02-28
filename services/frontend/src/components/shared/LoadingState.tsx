import { Skeleton } from '@/components/ui/skeleton'

interface Props {
  rows?: number
}

export default function LoadingState({ rows = 3 }: Props) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-20 w-full rounded-xl" />
      ))}
    </div>
  )
}
