import { useMemo, useCallback, useState, useEffect } from 'react';
import { useWebSocketContext } from '../contexts/WebSocketContext';

/**
 * 未读通知计数 Hook
 *
 * 单一数据源：
 * - lastReadAt 持久化在 localStorage（key: notif_last_read）
 * - 通过 WebSocketContext 的 events 计算未读数
 * - App.tsx 与 NotificationCenter 共用此 hook，保证未读数一致
 */
const LAST_READ_KEY = 'notif_last_read';

export function useUnreadNotifications() {
  const { events } = useWebSocketContext();

  const [lastReadAt, setLastReadAt] = useState<number>(() => {
    if (typeof window === 'undefined') return Date.now();
    return Number(localStorage.getItem(LAST_READ_KEY) || Date.now());
  });

  // 同步其他 tab/组件对 lastReadAt 的更新
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === LAST_READ_KEY && e.newValue) {
        setLastReadAt(Number(e.newValue));
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const unreadCount = useMemo(() => {
    return events.filter(e => e.timestamp > lastReadAt).length;
  }, [events, lastReadAt]);

  const markAllRead = useCallback(() => {
    const now = Date.now();
    setLastReadAt(now);
    try {
      localStorage.setItem(LAST_READ_KEY, String(now));
    } catch {
      // ignore quota errors
    }
  }, []);

  return { unreadCount, markAllRead, lastReadAt };
}
