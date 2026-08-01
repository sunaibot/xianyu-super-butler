import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: React.ElementType;
  iconPosition?: 'left' | 'right';
  error?: boolean;
}

/**
 * 原子输入框组件
 * 统一封装 ios-input 样式，支持图标
 * 触摸优化：移动端 font-size 16px 防 iOS 缩放
 */
export const Input: React.FC<InputProps> = ({
  icon: Icon,
  iconPosition = 'left',
  error = false,
  className = '',
  ...rest
}) => {
  if (Icon) {
    return (
      <div className="relative group">
        <Icon
          className={`absolute top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black transition-colors ${
            iconPosition === 'left' ? 'left-4' : 'right-4'
          }`}
        />
        <input
          {...rest}
          className={`ios-input w-full ${iconPosition === 'left' ? 'pl-12' : 'pr-12'} px-4 py-3 rounded-2xl text-sm h-12 ${
            error ? 'border-red-300 bg-red-50' : ''
          } ${className}`}
        />
      </div>
    );
  }

  return (
    <input
      {...rest}
      className={`ios-input w-full px-4 py-3 rounded-2xl text-sm h-12 ${error ? 'border-red-300 bg-red-50' : ''} ${className}`}
    />
  );
};

export default Input;
