import React, { useState, useCallback, useEffect, useRef } from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import { Button } from './Button';
import { registerConfirmAPI, ConfirmAPI, ConfirmOptions } from '../../hooks/useConfirm';

/**
 * 确认对话框组件
 * 替代原生 confirm()，提供统一外观与异步 Promise 接口
 * 配合 useConfirm hook 使用
 */
const ConfirmDialog: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions>({});
  const resolverRef = useRef<((ok: boolean) => void) | null>(null);

  const show = useCallback((opts: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setOptions(opts);
      setVisible(true);
    });
  }, []);

  const handleResolve = useCallback((ok: boolean) => {
    setVisible(false);
    if (resolverRef.current) {
      resolverRef.current(ok);
      resolverRef.current = null;
    }
  }, []);

  // 注册到全局，供 useConfirm 调用
  useEffect(() => {
    const api: ConfirmAPI = { show };
    registerConfirmAPI(api);
    return () => registerConfirmAPI(null);
  }, [show]);

  // Esc 取消
  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleResolve(false);
      if (e.key === 'Enter') handleResolve(true);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, handleResolve]);

  if (!visible) return null;

  const variant = options.variant || 'primary';
  const Icon = variant === 'danger' ? AlertTriangle : Info;
  const iconColor = variant === 'danger' ? 'text-red-500' : 'text-[#FFE815]';

  return (
    <div className="modal-overlay" onClick={() => handleResolve(false)}>
      <div
        className="modal-container animate-slide-up"
        style={{ maxWidth: '28rem' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-body pt-10 pb-6 text-center">
          <div className="w-14 h-14 rounded-2xl bg-gray-50 flex items-center justify-center mx-auto mb-4">
            <Icon className={`w-7 h-7 ${iconColor}`} />
          </div>
          {options.title && (
            <h3 className="text-lg font-extrabold text-gray-900 mb-2">{options.title}</h3>
          )}
          {options.content && (
            <p className="text-sm text-gray-500 whitespace-pre-wrap">{options.content}</p>
          )}
        </div>
        <div className="modal-footer flex gap-3 pt-0">
          <Button
            variant="secondary"
            fullWidth
            size="lg"
            onClick={() => handleResolve(false)}
          >
            {options.cancelText || '取消'}
          </Button>
          <Button
            variant={variant === 'danger' ? 'danger' : 'primary'}
            fullWidth
            size="lg"
            onClick={() => handleResolve(true)}
          >
            {options.confirmText || '确认'}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
