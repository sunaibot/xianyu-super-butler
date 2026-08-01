import React, { createContext, useContext, useState, useCallback, useRef, useMemo } from 'react';

/**
 * 跨页面联动跳转上下文
 * - navigate(tab, params?) 切换页面并携带过滤/高亮参数
 * - 各业务组件消费 navigateParams 实现联动（如订单列表接收 item_id 过滤）
 */

export type TabId =
  | 'dashboard'
  | 'accounts'
  | 'orders'
  | 'cards'
  | 'items'
  | 'keywords'
  | 'kb'
  | 'rules'
  | 'users'
  | 'settings';

export interface NavigateParams {
  /** 高亮某条记录（如商品 id） */
  highlight?: string;
  /** 过滤条件（如 { item_id, cookie_id, status }） */
  filter?: Record<string, any>;
  /** 其他任意参数 */
  [key: string]: any;
}

export interface NavigateContextValue {
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  /** 当前页面的联动参数 */
  navigateParams: NavigateParams | null;
  /** 跳转并携带参数 */
  navigate: (tab: TabId, params?: NavigateParams) => void;
  /** 清除联动参数（业务组件消费后调用） */
  consumeParams: () => NavigateParams | null;
}

const NavigateContext = createContext<NavigateContextValue | null>(null);

export const NavigateProvider: React.FC<{
  children: React.ReactNode;
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
}> = ({ children, activeTab, setActiveTab }) => {
  const [navigateParams, setNavigateParams] = useState<NavigateParams | null>(null);
  // 用 ref 缓存最新参数，避免业务组件 useEffect 依赖丢失
  const paramsRef = useRef<NavigateParams | null>(null);

  const navigate = useCallback((tab: TabId, params?: NavigateParams) => {
    paramsRef.current = params ?? null;
    setNavigateParams(params ?? null);
    setActiveTab(tab);
  }, [setActiveTab]);

  const consumeParams = useCallback(() => {
    const p = paramsRef.current;
    paramsRef.current = null;
    setNavigateParams(null);
    return p;
  }, []);

  return (
    <NavigateContext.Provider value={useMemo(() => ({ activeTab, setActiveTab, navigateParams, navigate, consumeParams }), [activeTab, setActiveTab, navigateParams, navigate, consumeParams])}>
      {children}
    </NavigateContext.Provider>
  );
};

export function useNavigate(): NavigateContextValue {
  const ctx = useContext(NavigateContext);
  if (!ctx) {
    throw new Error('useNavigate must be used within NavigateProvider');
  }
  return ctx;
}
