import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useIsMobile } from '../../hooks/useMediaQuery';

export type DrawerSide = 'left' | 'right' | 'bottom';

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  side?: DrawerSide;
  width?: string; // left/right 宽度（桌面端生效，移动端自动全屏）
  closeOnOverlay?: boolean;
  /** 移动端是否自动全屏（默认 true） */
  fullscreenOnMobile?: boolean;
}

/**
 * 抽屉组件
 * 从左/右/底部滑出，移动端导航与筛选用
 * - 移动端 left/right 自动全屏（覆盖 100vw / 100vh）
 * - bottom 在移动端自动占满屏幕高度的 92%
 */
export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  children,
  side = 'right',
  width = '20rem',
  closeOnOverlay = true,
  fullscreenOnMobile = true,
}) => {
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const overlayCls = 'fixed inset-0 z-[9999] bg-black/40 backdrop-blur-sm';

  // 移动端 left/right 全屏，桌面端按 width 显示
  const mobileFullscreen = fullscreenOnMobile && isMobile;

  const panelCls: Record<DrawerSide, string> = {
    left: 'fixed top-0 left-0 h-full bg-white shadow-2xl flex flex-col',
    right: 'fixed top-0 right-0 h-full bg-white shadow-2xl flex flex-col',
    bottom: 'fixed bottom-0 left-0 right-0 bg-white rounded-t-3xl shadow-2xl flex flex-col',
  };

  // 移动端 bottom 占 92vh，桌面端保持 85vh
  const maxHeight = side === 'bottom'
    ? (mobileFullscreen ? '92vh' : '85vh')
    : undefined;

  const panelStyle: React.CSSProperties =
    side === 'bottom'
      ? { maxHeight }
      : mobileFullscreen
        ? { width: '100vw', maxWidth: '100vw' }
        : { width, maxWidth: '85vw' };

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (closeOnOverlay && e.target === e.currentTarget) onClose();
  };

  // 动画类
  const animCls: Record<DrawerSide, string> = {
    left: 'animate-[fadeIn_0.2s_ease] translate-x-0',
    right: 'animate-[fadeIn_0.2s_ease]',
    bottom: 'animate-slide-up',
  };

  return createPortal(
    <div className={overlayCls} onClick={handleOverlayClick}>
      <div className={`${panelCls[side]} ${animCls[side]}`} style={panelStyle}>
        {title != null && (
          <div
            className="flex items-center justify-between px-5 py-4 border-b border-gray-100 flex-shrink-0"
            style={{ paddingTop: side === 'bottom' ? 'env(safe-area-inset-top)' : undefined }}
          >
            {typeof title === 'string' ? (
              <h3 className="font-bold text-gray-900">{title}</h3>
            ) : (
              title
            )}
            <button
              onClick={onClose}
              className="w-9 h-9 min-h-[36px] flex items-center justify-center rounded-xl text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              aria-label="关闭"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>,
    document.body
  );
};

export default Drawer;
