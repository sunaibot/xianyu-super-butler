import { useState, useCallback, useRef, useEffect } from 'react';

/**
 * 确认对话框 Hook：替代原生 confirm()
 * 配合 ConfirmDialog 组件使用
 *
 * @example
 * const confirm = useConfirm();
 * const handleDelete = async () => {
 *   const ok = await confirm({ title: '确认删除？', content: '此操作不可恢复' });
 *   if (ok) doDelete();
 * };
 * // 在组件树中渲染 <ConfirmDialog ref={confirm.ref} />
 */
export interface ConfirmOptions {
  title?: string;
  content?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'primary';
}

export interface ConfirmHandle {
  ref: React.MutableRefObject<ConfirmAPI | null>;
  (options: ConfirmOptions): Promise<boolean>;
}

export interface ConfirmAPI {
  show: (options: ConfirmOptions) => Promise<boolean>;
}

// 全局事件式实现，避免 Context Provider 嵌套
let _globalConfirmResolver: ((api: ConfirmAPI | null) => void) | null = null;
let _globalConfirmAPI: ConfirmAPI | null = null;

export function registerConfirmAPI(api: ConfirmAPI | null) {
  _globalConfirmAPI = api;
  if (_globalConfirmResolver) {
    _globalConfirmResolver(api);
    _globalConfirmResolver = null;
  }
}

export function useConfirm(): (options: ConfirmOptions) => Promise<boolean> {
  const ensure = useCallback(async (): Promise<ConfirmAPI | null> => {
    if (_globalConfirmAPI) return _globalConfirmAPI;
    // 等待 ConfirmDialog 挂载并注册
    return new Promise(resolve => {
      _globalConfirmResolver = resolve;
    });
  }, []);

  return useCallback(async (options: ConfirmOptions) => {
    const api = await ensure();
    if (!api) {
      // 降级到原生 confirm
      return window.confirm(options.title || options.content || '确认操作？');
    }
    return api.show(options);
  }, [ensure]);
}
