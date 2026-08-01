import React, { useState, useCallback } from 'react';
import DesktopSidebar from './DesktopSidebar';
import MobileTabBar from './MobileTabBar';
import MobileDrawer from './MobileDrawer';
import TopBar from './TopBar';
import { useUnreadNotifications } from '../../hooks/useUnreadNotifications';
import type { TabId } from '../../contexts/NavigateContext';

interface AppShellProps {
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  onLogout: () => void;
  children: React.ReactNode;
  onOpenSearch: () => void;
  onOpenNotifications: () => void;
}

/**
 * 应用主布局壳
 * - 桌面（≥769px）：左侧 DesktopSidebar + 主内容 ml-64
 * - 移动端（<769px）：TopBar 顶栏 + 主内容 + MobileTabBar 底栏 + MobileDrawer 抽屉
 *
 * 替代 App.tsx 原有的 Sidebar + main 结构
 *
 * 未读通知计数在本组件内部通过 useUnreadNotifications 消费，
 * 保证 TopBar 铃铛角标与 NotificationCenter 一致，App.tsx 无需传入。
 */
const AppShell: React.FC<AppShellProps> = ({
  activeTab,
  setActiveTab,
  onLogout,
  children,
  onOpenSearch,
  onOpenNotifications,
}) => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { unreadCount } = useUnreadNotifications();

  const handleOpenDrawer = useCallback(() => setDrawerOpen(true), []);
  const handleCloseDrawer = useCallback(() => setDrawerOpen(false), []);

  return (
    <div className="flex min-h-screen bg-[#F4F5F7] text-[#111]">
      <DesktopSidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onLogout={onLogout}
      />

      <MobileDrawer
        isOpen={drawerOpen}
        onClose={handleCloseDrawer}
        setActiveTab={setActiveTab}
        onLogout={onLogout}
      />

      <div className="flex-1 md:ml-64 flex flex-col min-h-screen">
        <TopBar
          activeTab={activeTab}
          onOpenDrawer={handleOpenDrawer}
          onOpenSearch={onOpenSearch}
          onOpenNotifications={onOpenNotifications}
          unreadCount={unreadCount}
        />

        <main className="flex-1 p-4 md:p-8 lg:p-10 overflow-y-auto">
          <div className="fixed top-0 right-0 w-[800px] h-[800px] bg-gradient-to-bl from-yellow-50 to-transparent rounded-full blur-[120px] pointer-events-none -z-10 opacity-60" />
          <div className="max-w-[1400px] mx-auto pb-24 md:pb-10">
            {children}
          </div>
        </main>
      </div>

      <MobileTabBar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onMore={handleOpenDrawer}
      />
    </div>
  );
};

export default AppShell;
