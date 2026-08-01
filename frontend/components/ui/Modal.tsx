import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  /** 关闭时是否卸载内容（默认 false，保留状态） */
  destroyOnClose?: boolean;
  closeOnOverlay?: boolean;
}

const SIZE_MAP: Record<NonNullable<ModalProps['size']>, string> = {
  sm: 'max-w-md',
  md: 'max-w-2xl',
  lg: 'max-w-4xl',
  xl: 'max-w-6xl',
};

/**
 * 原子模态框组件
 * 统一封装 modal-overlay/container/header/body/footer 结构（index.css:266-319）
 * 移动端自适应：max-w calc(100% - 2rem)
 */
export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  destroyOnClose = false,
  closeOnOverlay = true,
}) => {
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    // 锁定背景滚动
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (closeOnOverlay && e.target === e.currentTarget) onClose();
  };

  return createPortal(
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div className={`modal-container ${SIZE_MAP[size]} animate-slide-up`}>
        {title != null && (
          <div className="modal-header flex items-center justify-between">
            {typeof title === 'string' ? (
              <h3 className="text-xl font-extrabold text-gray-900">{title}</h3>
            ) : (
              title
            )}
            <button
              onClick={onClose}
              className="w-9 h-9 min-h-[36px] min-w-[36px] flex items-center justify-center rounded-xl text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors"
              aria-label="关闭"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
        <div className="modal-body">{destroyOnClose && !isOpen ? null : children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>,
    document.body
  );
};

export default Modal;
