import React from 'react';

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'default' | 'brand';

export interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  success: 'bg-green-100 text-green-700',
  warning: 'bg-yellow-100 text-yellow-800',
  error: 'bg-red-100 text-red-600',
  info: 'bg-blue-100 text-blue-700',
  default: 'bg-gray-100 text-gray-600',
  brand: 'bg-[#FFE815] text-black',
};

const DOT_COLORS: Record<BadgeVariant, string> = {
  success: 'bg-green-500',
  warning: 'bg-yellow-500',
  error: 'bg-red-500',
  info: 'bg-blue-500',
  default: 'bg-gray-400',
  brand: 'bg-black',
};

/**
 * 原子徽章组件
 * 统一 StatusBadge 等重复定义，支持 dot 模式
 */
export const Badge: React.FC<BadgeProps> = ({ variant = 'default', children, className = '', dot = false }) => {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${DOT_COLORS[variant]}`} />}
      {children}
    </span>
  );
};

/** 订单状态映射 → Badge variant */
export const orderStatusBadge = (status: string): { variant: BadgeVariant; label: string } => {
  const map: Record<string, { variant: BadgeVariant; label: string }> = {
    processing: { variant: 'warning', label: '处理中' },
    pending_ship: { variant: 'brand', label: '待发货' },
    shipped: { variant: 'info', label: '已发货' },
    completed: { variant: 'success', label: '已完成' },
    cancelled: { variant: 'default', label: '已取消' },
    refunding: { variant: 'error', label: '退款中' },
  };
  return map[status] || { variant: 'default', label: status };
};

/** 订单状态徽章（业务快捷封装） */
export const OrderStatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const { variant, label } = orderStatusBadge(status);
  return <Badge variant={variant}>{label}</Badge>;
};

export default Badge;
