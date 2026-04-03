import { lazy, Suspense } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { User } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'

const VrmCanvas = lazy(() => import('./VrmCanvas'))

export default function AvatarPanel() {
  return (
    <Card className="flex flex-col overflow-hidden">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <User className="h-4 w-4 text-primary" />
          Avatar
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 p-0 min-h-0">
        <Suspense fallback={<Skeleton className="h-64 lg:h-72 w-full" />}>
          <VrmCanvas className="h-64 lg:h-72 w-full" />
        </Suspense>
      </CardContent>
    </Card>
  )
}
