import React from 'react';

export interface CardProps {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  hover?: boolean;
  onClick?: () => void;
}

/**
 * 原子卡片组件
 * 统一封装 ios-card 样式，支持 title/actions 插槽
 */
export const Card: React.FC<CardProps> = ({
  title,
  actions,
  children,
  className = '',
  bodyClassName = '',
  hover = false,
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`ios-card overflow-hidden ${hover ? 'cursor-pointer hover:translate-y-[-4px]' : ''} ${className}`}
    >
      {(title || actions) && (
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-50">
          {typeof title === 'string' ? (
            <h3 className="font-bold text-gray-900 text-base">{title}</h3>
          ) : (
            title
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={`p-6 ${bodyClassName}`}>{children}</div>
    </div>
  );
};

export default Card;
