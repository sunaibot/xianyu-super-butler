import React from 'react';
import { MoreHorizontal } from 'lucide-react';
import { CORE_NAV_ITEMS } from './nav';
import type { TabId } from '../../contexts/NavigateContext';

interface MobileTabBarProps {
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  onMore: () => void;
}

/**
 * 移动端底部 Tab Bar（<769px）
 * 5 核心 Tab + "更多"按钮打开抽屉
 * 固定底部，含安全区适配
 */
const MobileTabBar: React.FC<MobileTabBarProps> = ({ activeTab, setActiveTab, onMore }) => {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-tabbar bg-white/95 backdrop-blur-xl border-t border-gray-100 flex items-stretch h-16 pb-safe-bottom">
      {CORE_NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;
        return (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className="flex-1 flex flex-col items-center justify-center gap-0.5 min-h-[44px] relative"
          >
            <Icon className={`w-5 h-5 transition-colors ${isActive ? 'text-black' : 'text-gray-400'}`} />
            <span className={`text-[10px] font-semibold transition-colors ${isActive ? 'text-black' : 'text-gray-400'}`}>
              {item.label}
            </span>
            {isActive && <span className="absolute top-0 w-8 h-0.5 bg-[#FFE815] rounded-full" />}
          </button>
        );
      })}
      <button
        onClick={onMore}
        className="flex-1 flex flex-col items-center justify-center gap-0.5 min-h-[44px]"
      >
        <MoreHorizontal className="w-5 h-5 text-gray-400" />
        <span className="text-[10px] font-semibold text-gray-400">更多</span>
      </button>
    </nav>
  );
};

export default MobileTabBar;
