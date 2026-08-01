import React from 'react';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

/**
 * 原子多行文本框组件
 * 统一封装 ios-input 样式
 */
export const Textarea: React.FC<TextareaProps> = ({ error = false, className = '', ...rest }) => {
  return (
    <textarea
      {...rest}
      className={`ios-input w-full px-4 py-3 rounded-2xl text-sm resize-y min-h-[96px] ${
        error ? 'border-red-300 bg-red-50' : ''
      } ${className}`}
    />
  );
};

export default Textarea;
