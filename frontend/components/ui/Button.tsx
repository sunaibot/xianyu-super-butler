import React from 'react';
import { Loader2 } from 'lucide-react';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ElementType;
  iconPosition?: 'left' | 'right';
  fullWidth?: boolean;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'ios-btn-primary',
  secondary: 'ios-btn-secondary',
  danger: 'ios-btn-danger',
  ghost: 'bg-transparent text-gray-600 hover:bg-gray-100 font-semibold',
  outline: 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 font-semibold',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'h-9 px-3 text-sm rounded-xl min-h-[36px]',
  md: 'h-11 px-5 text-sm rounded-2xl min-h-[44px]',
  lg: 'h-14 px-6 text-base rounded-2xl min-h-[48px]',
};

/**
 * 原子按钮组件
 * 统一封装 ios-btn-* 样式，支持 variant/size/loading/icon
 * 触摸优化：最小高度 44px
 */
export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon: Icon,
  iconPosition = 'left',
  fullWidth = false,
  children,
  disabled,
  className = '',
  ...rest
}) => {
  const isDisabled = disabled || loading;

  return (
    <button
      {...rest}
      disabled={isDisabled}
      className={`inline-flex items-center justify-center gap-2 transition-all duration-200 select-none ${
        VARIANT_CLASSES[variant]
      } ${SIZE_CLASSES[size]} ${fullWidth ? 'w-full' : ''} ${isDisabled ? 'opacity-60 cursor-not-allowed' : ''} ${className}`}
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {!loading && Icon && iconPosition === 'left' && <Icon className="w-4 h-4" />}
      {children}
      {!loading && Icon && iconPosition === 'right' && <Icon className="w-4 h-4" />}
    </button>
  );
};

export default Button;
