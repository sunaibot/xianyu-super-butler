import React from 'react';
import { LogOut, X } from 'lucide-react';
import { Drawer } from '../ui/Drawer';
import { MORE_NAV_ITEMS } from './nav';
import type { TabId } from '../../contexts/NavigateContext';

interface MobileDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  setActiveTab: (tab: TabId) => void;
  onLogout: () => void;
}

/**
 * 移动端"更多"抽屉
 * 从右侧滑出，包含非核心导航项 + 退出登录
 */
const MobileDrawer: React.FC<MobileDrawerProps> = ({ isOpen, onClose, setActiveTab, onLogout }) => {
  const handleSelect = (id: TabId) => {
    setActiveTab(id);
    onClose();
  };

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      side="right"
      width="18rem"
      title={
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#FFE815] rounded-lg flex items-center justify-center">
            <span className="text-black font-extrabold text-sm">闲</span>
          </div>
          <span>更多功能</span>
        </div>
      }
    >
      <nav className="space-y-1.5">
        {MORE_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => handleSelect(item.id)}
              className="w-full flex items-center gap-3 px-4 py-3.5 min-h-[48px] rounded-2xl text-gray-700 hover:bg-gray-50 active:bg-gray-100 transition-colors font-medium"
            >
              <Icon className="w-5 h-5 text-gray-400" />
              <span className="text-sm">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-6 pt-6 border-t border-gray-100">
        <button
          onClick={() => {
            onLogout();
            onClose();
          }}
          className="w-full flex items-center gap-3 px-4 py-3.5 min-h-[48px] rounded-2xl text-red-500 hover:bg-red-50 transition-colors font-medium"
        >
          <LogOut className="w-5 h-5" />
          <span className="text-sm">退出登录</span>
        </button>
      </div>
    </Drawer>
  );
};

export default MobileDrawer;
