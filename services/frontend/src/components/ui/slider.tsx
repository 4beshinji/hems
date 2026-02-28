import * as React from 'react'
import { cn } from '@/lib/utils'

interface SliderProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange'> {
  onValueChange?: (value: number) => void
  onValueCommit?: (value: number) => void
}

const Slider = React.forwardRef<HTMLInputElement, SliderProps>(
  ({ className, onValueChange, onValueCommit, ...props }, ref) => (
    <input
      type="range"
      ref={ref}
      className={cn(
        'w-full h-2 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary',
        className
      )}
      onChange={(e) => onValueChange?.(Number(e.target.value))}
      onMouseUp={(e) => onValueCommit?.(Number((e.target as HTMLInputElement).value))}
      onTouchEnd={(e) => onValueCommit?.(Number((e.target as HTMLInputElement).value))}
      {...props}
    />
  )
)
Slider.displayName = 'Slider'

export { Slider }
