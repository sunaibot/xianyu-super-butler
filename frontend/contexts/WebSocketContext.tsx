import React, { createContext, useContext, useEffect, useCallback, ReactNode } from 'react';
import { useWebSocket, WsEvent } from '../hooks/useWebSocket';

interface WebSocketContextValue {
  connected: boolean;
  events: WsEvent[];
  onEvent: (type: string, handler: (event: WsEvent) => void) => () => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export const WebSocketProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { connected, events } = useWebSocket();

  const handlerRefs = React.useRef<Map<string, Set<(event: WsEvent) => void>>>(new Map());

  const onEvent = useCallback((type: string, handler: (event: WsEvent) => void) => {
    if (!handlerRefs.current.has(type)) {
      handlerRefs.current.set(type, new Set());
    }
    handlerRefs.current.get(type)!.add(handler);

    return () => {
      handlerRefs.current.get(type)?.delete(handler);
    };
  }, []);

  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0];
    const handlers = handlerRefs.current.get(latest.type);
    if (handlers) {
      handlers.forEach(h => {
        try { h(latest); } catch (e) { console.error('WS handler error:', e); }
      });
    }
  }, [events]);

  return (
    <WebSocketContext.Provider value={{ connected, events, onEvent }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocketContext = (): WebSocketContextValue => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
};
