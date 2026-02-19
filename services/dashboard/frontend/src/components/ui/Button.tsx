import { forwardRef } from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import { clsx } from 'clsx';

export interface ButtonProps extends HTMLMotionProps<"button"> {
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
    size?: 'small' | 'medium' | 'large';
    loading?: boolean;
    fullWidth?: boolean;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
    (
        {
            variant = 'primary',
            size = 'medium',
            loading = false,
            fullWidth = false,
            className,
            children,
            disabled,
            ...props
        },
        ref
    ) => {
        const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

        const variantStyles = {
            primary: 'bg-[var(--primary-500)] text-white hover:bg-[var(--primary-700)] focus:ring-[var(--primary-500)] active:bg-[var(--primary-900)]',
            secondary: 'bg-white text-[var(--primary-500)] border-2 border-[var(--primary-500)] hover:bg-[var(--primary-50)] focus:ring-[var(--primary-500)]',
            ghost: 'bg-transparent text-[var(--gray-700)] hover:bg-[var(--gray-100)] focus:ring-[var(--gray-400)]',
            danger: 'bg-[var(--error-500)] text-white hover:bg-[var(--error-700)] focus:ring-[var(--error-500)]',
        };

        const sizeStyles = {
            small: 'px-3 py-2 text-sm min-h-[36px]',
            medium: 'px-6 py-3 text-base min-h-[44px]',
            large: 'px-8 py-4 text-lg min-h-[52px]',
        };

        const widthStyles = fullWidth ? 'w-full' : '';

        return (
            <motion.button
                ref={ref}
                className={clsx(
                    baseStyles,
                    variantStyles[variant],
                    sizeStyles[size],
                    widthStyles,
                    className
                )}
                disabled={disabled || loading}
                whileHover={{ scale: disabled || loading ? 1 : 1.02 }}
                whileTap={{ scale: disabled || loading ? 1 : 0.98 }}
                {...props}
            >
                {loading ? (
                    <>
                        <svg
                            className="animate-spin -ml-1 mr-2 h-4 w-4"
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                        >
                            <circle
                                className="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                strokeWidth="4"
                            />
                            <path
                                className="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                            />
                        </svg>
                        読み込み中...
                    </>
                ) : (
                    children
                )}
            </motion.button>
        );
    }
);

Button.displayName = 'Button';

export default Button;
