import React from 'react';
import { ChevronDown } from 'lucide-react';

export interface SelectOption {
  label: string;
  value: string | number;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  error?: boolean;
}

/**
 * 原子下拉选择组件
 * 统一封装 ios-input 样式，右侧箭头图标
 */
export const Select: React.FC<SelectProps> = ({ options, error = false, className = '', children, ...rest }) => {
  return (
    <div className="relative">
      <select
        {...rest}
        className={`ios-input w-full appearance-none px-4 pr-10 py-3 rounded-2xl text-sm h-12 cursor-pointer ${
          error ? 'border-red-300 bg-red-50' : ''
        } ${className}`}
      >
        {options ? options.map(o => <option key={o.value} value={o.value}>{o.label}</option>) : children}
      </select>
      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
    </div>
  );
};

export default Select;
