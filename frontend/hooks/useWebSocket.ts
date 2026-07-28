import { useState, useEffect, useCallback, useRef } from 'react';

export interface WsEvent {
  type: string;
  data: any;
  timestamp: number;
}

interface UseWebSocketReturn {
  connected: boolean;
  events: WsEvent[];
  lastEvent: WsEvent | null;
  sendMessage: (type: string, data?: any) => void;
  clearEvents: () => void;
}

const MAX_EVENTS = 200;
const RECONNECT_DELAY = 3000;
const MAX_RECONNECT_ATTEMPTS = 20;  // 最大重连次数

export function useWebSocket(): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<WsEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectCountRef = useRef(0);
  const sessionTokenRef = useRef<string>('');
  const manualCloseRef = useRef(false);  // 是否主动关闭（如登出时）

  const getSessionToken = useCallback((): string => {
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'session') {
        return decodeURIComponent(value);
      }
    }
    return '';
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const port = window.location.port;
    const wsUrl = `${protocol}//${host}${port ? ':' + port : ''}/ws/events`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        const token = sessionTokenRef.current || getSessionToken();
        if (!token) {
          ws.close();
          return;
        }
        ws.send(JSON.stringify({ type: 'init', token }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'connected') {
            setConnected(true);
            reconnectCountRef.current = 0;
            return;
          }

          if (data.type === 'pong') return;

          if (data.type === 'snapshot' && Array.isArray(data.data)) {
            setEvents(prev => {
              const newEvents = [...data.data, ...prev];
              return newEvents.slice(0, MAX_EVENTS);
            });
            return;
          }

          if (data.type === 'error') {
            setConnected(false);
            ws.close();
            return;
          }

          setEvents(prev => {
            const newEvents = [data, ...prev];
            return newEvents.slice(0, MAX_EVENTS);
          });
        } catch (e) {
          console.error('WebSocket message parse error:', e);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;

        // 主动关闭不再重连
        if (manualCloseRef.current) return;

        reconnectCountRef.current++;
        if (reconnectCountRef.current > MAX_RECONNECT_ATTEMPTS) {
          console.warn(`WebSocket 重连次数已达上限 (${MAX_RECONNECT_ATTEMPTS})，停止重连`);
          return;
        }

        const delay = Math.min(RECONNECT_DELAY * Math.pow(1.5, reconnectCountRef.current - 1), 30000);

        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      console.error('WebSocket connection error:', e);
    }
  }, [getSessionToken]);

  const sendMessage = useCallback((type: string, data?: any) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, data }));
    }
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  useEffect(() => {
    sessionTokenRef.current = getSessionToken();
    connect();

    const heartbeatTimer = setInterval(() => {
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    return () => {
      clearInterval(heartbeatTimer);
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect, getSessionToken]);

  const lastEvent = events.length > 0 ? events[0] : null;

  return {
    connected,
    events,
    lastEvent,
    sendMessage,
    clearEvents,
  };
}
