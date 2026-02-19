import { HTMLAttributes, forwardRef, ReactNode } from 'react';
import { clsx } from 'clsx';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
    variant?: 'success' | 'warning' | 'error' | 'info' | 'gold' | 'xp' | 'neutral';
    size?: 'small' | 'medium';
    icon?: ReactNode;
}

const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
    (
        {
            variant = 'neutral',
            size = 'medium',
            icon,
            className,
            children,
            ...props
        },
        ref
    ) => {
        const baseStyles = 'inline-flex items-center gap-1 font-medium rounded-full transition-all';

        const variantStyles = {
            success: 'bg-[var(--success-50)] text-[var(--success-700)] border border-[var(--success-500)]',
            warning: 'bg-[var(--warning-50)] text-[var(--warning-700)] border border-[var(--warning-500)]',
            error: 'bg-[var(--error-50)] text-[var(--error-700)] border border-[var(--error-500)]',
            info: 'bg-[var(--info-50)] text-[var(--info-700)] border border-[var(--info-500)]',
            gold: 'bg-gradient-to-r from-yellow-100 to-amber-100 text-[var(--gold-dark)] border border-[var(--gold)]',
            xp: 'bg-gradient-to-r from-purple-100 to-pink-100 text-[var(--xp-purple-dark)] border border-[var(--xp-purple)]',
            neutral: 'bg-[var(--gray-100)] text-[var(--gray-700)] border border-[var(--gray-300)]',
        };

        const sizeStyles = {
            small: 'px-2 py-0.5 text-xs',
            medium: 'px-3 py-1 text-sm',
        };

        return (
            <span
                ref={ref}
                className={clsx(
                    baseStyles,
                    variantStyles[variant],
                    sizeStyles[size],
                    className
                )}
                {...props}
            >
                {icon && <span className="flex-shrink-0">{icon}</span>}
                {children}
            </span>
        );
    }
);

Badge.displayName = 'Badge';

export default Badge;
