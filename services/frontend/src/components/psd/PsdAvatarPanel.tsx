/**
 * PSD 立ち絵アバター パネル
 *
 * ダッシュボード右カラムに直接インライン描画する。
 * VRM のポータル+固定位置方式は使わない。
 *
 * videofactory の CharacterConfig に倣い、
 * Card 内にアスペクト比固定のコンテナを設けて立ち絵を配置する。
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { User } from 'lucide-react'
import { PsdAvatar } from './PsdAvatar'
import { usePsdState } from './usePsdState'

export default function PsdAvatarPanel() {
  const state = usePsdState()

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <User className="h-4 w-4 text-primary" />
          Avatar
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="w-full aspect-[3/4] relative overflow-hidden">
          <PsdAvatar state={state} className="absolute inset-0" />
        </div>
      </CardContent>
    </Card>
  )
}
