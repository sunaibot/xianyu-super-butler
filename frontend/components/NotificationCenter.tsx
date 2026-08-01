import React, { useEffect } from 'react';
import { Drawer } from './ui/Drawer';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import { useNavigate } from '../contexts/NavigateContext';
import { useUnreadNotifications } from '../hooks/useUnreadNotifications';
import { Bell, ShoppingCart, Package, Truck, MessageSquare, Activity, AlertCircle, CheckCircle2 } from 'lucide-react';
import type { WsEvent } from '../hooks/useWebSocket';
import type { TabId } from '../contexts/NavigateContext';

interface NotificationCenterProps {
  isOpen: boolean;
  onClose: () => void;
}

// 事件类型 → 显示配置
const EVENT_CONFIG: Record<string, { icon: React.ElementType; label: string; color: string; tab: TabId }> = {
  new_order: { icon: ShoppingCart, label: '新订单', color: 'text-orange-500', tab: 'orders' },
  order_status_changed: { icon: Package, label: '订单状态变更', color: 'text-blue-500', tab: 'orders' },
  delivery_completed: { icon: Truck, label: '发货完成', color: 'text-green-500', tab: 'orders' },
  message_received: { icon: MessageSquare, label: '新消息', color: 'text-purple-500', tab: 'accounts' },
  account_status: { icon: Activity, label: '账号状态', color: 'text-yellow-600', tab: 'accounts' },
  system_log: { icon: AlertCircle, label: '系统日志', color: 'text-gray-500', tab: 'dashboard' },
};

const formatTime = (ts: number): string => {
  const diff = Date.now() - ts;
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

/** 摘要事件数据 */
const summarize = (e: WsEvent): string => {
  const d = e.data || {};
  if (e.type === 'new_order') return `订单 ${d.order_id || ''} ${d.item_title || ''}`.trim();
  if (e.type === 'order_status_changed') return `订单 ${d.order_id || ''}: ${d.old_status || ''} → ${d.new_status || ''}`.trim();
  if (e.type === 'delivery_completed') return `订单 ${d.order_id || ''} 已发货 (${d.delivery_type || ''})`.trim();
  if (e.type === 'message_received') return `${d.sender_id || '买家'}: ${String(d.content || '').slice(0, 30)}`.trim();
  if (e.type === 'account_status') return `账号 ${d.cookie_id || ''}: ${d.status || ''}`.trim();
  if (e.type === 'system_log') return `${d.level || ''} ${d.message || ''}`.trim();
  return JSON.stringify(d).slice(0, 60);
};

/**
 * 通知中心
 * 聚合 WebSocket 实时事件，支持点击跳转
 * 打开时自动标记已读（localStorage 记录最后查看时间）
 */
const NotificationCenter: React.FC<NotificationCenterProps> = ({ isOpen, onClose }) => {
  const { events } = useWebSocketContext();
  const { navigate } = useNavigate();
  const { unreadCount, lastReadAt, markAllRead } = useUnreadNotifications();

  // 打开时标记已读
  useEffect(() => {
    if (isOpen) {
      markAllRead();
    }
  }, [isOpen, markAllRead]);

  const handleEventClick = (e: WsEvent) => {
    const cfg = EVENT_CONFIG[e.type];
    if (cfg) {
      navigate(cfg.tab);
    }
    onClose();
  };

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      side="right"
      width="24rem"
      title={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-[#FFE815]" />
            <span>通知中心</span>
          </div>
          {unreadCount > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-red-500 text-white font-bold">
              {unreadCount} 未读
            </span>
          )}
        </div>
      }
    >
      {events.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <CheckCircle2 className="w-12 h-12 text-gray-200 mb-3" />
          <p className="text-sm text-gray-400">暂无通知</p>
          <p className="text-xs text-gray-300 mt-1">实时事件将在此显示</p>
        </div>
      ) : (
        <div className="space-y-2">
          {events.slice(0, 50).map((e, idx) => {
            const cfg = EVENT_CONFIG[e.type] || { icon: AlertCircle, label: e.type, color: 'text-gray-400', tab: 'dashboard' as TabId };
            const Icon = cfg.icon;
            const isUnread = e.timestamp > lastReadAt;
            return (
              <button
                key={`${e.timestamp}-${idx}`}
                onClick={() => handleEventClick(e)}
                className={`w-full text-left p-3 rounded-2xl transition-colors flex items-start gap-3 min-h-[56px] ${
                  isUnread ? 'bg-yellow-50/60 hover:bg-yellow-50' : 'hover:bg-gray-50'
                }`}
              >
                <div className={`flex-shrink-0 w-9 h-9 rounded-xl bg-gray-50 flex items-center justify-center ${cfg.color}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <span className="text-sm font-bold text-gray-900">{cfg.label}</span>
                    <span className="text-xs text-gray-400 flex-shrink-0">{formatTime(e.timestamp)}</span>
                  </div>
                  <p className="text-xs text-gray-500 line-clamp-2 break-all">{summarize(e)}</p>
                </div>
                {isUnread && <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0 mt-1" />}
              </button>
            );
          })}
        </div>
      )}
    </Drawer>
  );
};

export default NotificationCenter;
