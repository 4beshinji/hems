import { forwardRef, ReactNode } from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import { clsx } from 'clsx';

export interface CardProps extends HTMLMotionProps<"div"> {
    children?: ReactNode;
    elevation?: 1 | 2 | 3 | 4;
    padding?: 'none' | 'small' | 'medium' | 'large';
    header?: ReactNode;
    footer?: ReactNode;
    hoverable?: boolean;
}

const Card = forwardRef<HTMLDivElement, CardProps>(
    (
        {
            elevation = 2,
            padding = 'medium',
            header,
            footer,
            hoverable = false,
            className,
            children,
            ...props
        },
        ref
    ) => {
        const baseStyles = 'bg-white rounded-xl transition-all';

        const elevationStyles = {
            1: 'elevation-1',
            2: 'elevation-2',
            3: 'elevation-3',
            4: 'elevation-4',
        };

        const paddingStyles = {
            none: '',
            small: 'p-4',
            medium: 'p-6',
            large: 'p-8',
        };

        const hoverStyles = hoverable
            ? 'hover:elevation-3 hover:-translate-y-1 cursor-pointer'
            : '';

        return (
            <motion.div
                ref={ref}
                className={clsx(
                    baseStyles,
                    elevationStyles[elevation],
                    hoverStyles,
                    className
                )}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                {...props}
            >
                {header && (
                    <div className={clsx('border-b border-[var(--gray-200)]', paddingStyles[padding], 'pb-4')}>
                        {header}
                    </div>
                )}
                <div className={clsx(paddingStyles[padding])}>{children}</div>
                {footer && (
                    <div className={clsx('border-t border-[var(--gray-200)]', paddingStyles[padding], 'pt-4')}>
                        {footer}
                    </div>
                )}
            </motion.div>
        );
    }
);

Card.displayName = 'Card';

export default Card;
