import React from 'react';
import { Inbox } from 'lucide-react';

export interface EmptyStateProps {
  icon?: React.ElementType;
  title?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

/**
 * 空状态占位组件
 * 统一列表为空时的展示
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon = Inbox,
  title = '暂无数据',
  description,
  action,
  className = '',
}) => {
  return (
    <div className={`flex flex-col items-center justify-center py-16 px-4 text-center ${className}`}>
      <div className="w-16 h-16 rounded-2xl bg-gray-50 flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-gray-300" />
      </div>
      <h3 className="text-base font-bold text-gray-900 mb-1">{title}</h3>
      {description && <p className="text-sm text-gray-500 mb-4 max-w-xs">{description}</p>}
      {action}
    </div>
  );
};

export default EmptyState;
