import React, { useState } from 'react';
import { Menu, Search, Bell, Wifi, WifiOff, Command } from 'lucide-react';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import { NAV_LABEL_MAP } from './nav';
import type { TabId } from '../../contexts/NavigateContext';

interface TopBarProps {
  activeTab: TabId;
  onOpenDrawer: () => void;
  onOpenSearch: () => void;
  onOpenNotifications: () => void;
  unreadCount?: number;
}

/**
 * 顶部栏
 * - 桌面：页面标题 + 搜索按钮 + WS 状态 + 通知 + ⌘K 提示
 * - 移动端：左 hamburger + 标题 + 右搜索/铃铛
 */
const TopBar: React.FC<TopBarProps> = ({
  activeTab,
  onOpenDrawer,
  onOpenSearch,
  onOpenNotifications,
  unreadCount = 0,
}) => {
  const isMobile = useIsMobile();
  const { connected } = useWebSocketContext();
  const title = NAV_LABEL_MAP[activeTab] || '闲鱼智控';

  if (isMobile) {
    return (
      <header
        className="md:hidden sticky top-0 z-topbar bg-white/90 backdrop-blur-xl border-b border-gray-100 px-4 h-14 flex items-center justify-between"
        style={{ paddingTop: 'env(safe-area-inset-top)', height: 'calc(3.5rem + env(safe-area-inset-top))' }}
      >
        <button
          onClick={onOpenDrawer}
          className="w-10 h-10 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-gray-600 hover:bg-gray-100"
          aria-label="打开菜单"
        >
          <Menu className="w-5 h-5" />
        </button>
        <h1 className="text-base font-extrabold text-gray-900 truncate">{title}</h1>
        <div className="flex items-center gap-1">
          <button
            onClick={onOpenSearch}
            className="w-10 h-10 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-gray-600 hover:bg-gray-100"
            aria-label="搜索"
          >
            <Search className="w-5 h-5" />
          </button>
          <button
            onClick={onOpenNotifications}
            className="relative w-10 h-10 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-gray-600 hover:bg-gray-100"
            aria-label="通知"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>
        </div>
      </header>
    );
  }

  return (
    <header className="hidden md:flex sticky top-0 z-topbar bg-white/70 backdrop-blur-xl border-b border-gray-50 px-8 h-14 items-center justify-between">
      <h1 className="text-lg font-extrabold text-gray-900">{title}</h1>

      <div className="flex items-center gap-3">
        <button
          onClick={onOpenSearch}
          className="flex items-center gap-2 h-10 px-4 rounded-xl bg-gray-50 hover:bg-gray-100 text-gray-400 text-sm transition-colors min-h-[40px]"
        >
          <Search className="w-4 h-4" />
          <span>搜索商品、订单、账号…</span>
          <kbd className="ml-2 px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] font-mono text-gray-400">
            <Command className="w-3 h-3 inline" />K
          </kbd>
        </button>

        <button
          onClick={onOpenNotifications}
          className="relative w-10 h-10 min-h-[40px] flex items-center justify-center rounded-xl text-gray-500 hover:bg-gray-100"
          aria-label="通知"
        >
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white border border-gray-100 text-xs font-medium">
          {connected ? (
            <>
              <Wifi className="w-3.5 h-3.5 text-green-500" />
              <span className="text-green-700">实时连接</span>
            </>
          ) : (
            <>
              <WifiOff className="w-3.5 h-3.5 text-gray-400 animate-pulse" />
              <span className="text-gray-500">连接中</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
};

export default TopBar;
