import React from 'react';

export interface SkeletonProps {
  className?: string;
  /** 圆形骨架 */
  circle?: boolean;
  /** 行数（多行文本骨架） */
  lines?: number;
}

/**
 * 骨架屏组件
 * 封装 loading-skeleton 动画
 */
export const Skeleton: React.FC<SkeletonProps> = ({ className = '', circle = false, lines }) => {
  if (lines && lines > 0) {
    return (
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className="loading-skeleton h-4 rounded-lg"
            style={{ width: i === lines - 1 ? '60%' : '100%' }}
          />
        ))}
      </div>
    );
  }
  return (
    <div
      className={`loading-skeleton ${circle ? 'rounded-full' : 'rounded-lg'} ${className}`}
    />
  );
};

/** 卡片骨架（列表加载占位） */
export const CardSkeleton: React.FC = () => (
  <div className="ios-card p-6 space-y-4">
    <Skeleton className="h-6 w-1/3" />
    <Skeleton lines={3} />
    <div className="flex gap-2">
      <Skeleton className="h-9 w-20" />
      <Skeleton className="h-9 w-20" />
    </div>
  </div>
);

export default Skeleton;
