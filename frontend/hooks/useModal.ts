import { useState, useCallback } from 'react';

/**
 * 统一模态框开关 Hook
 * @returns { isOpen, open, close, toggle, setOpen }
 *
 * @example
 * const modal = useModal();
 * <button onClick={modal.open} />
 * {modal.isOpen && <Modal onClose={modal.close} />}
 */
export interface UseModalReturn {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  setOpen: (v: boolean) => void;
}

export function useModal(initial: boolean = false): UseModalReturn {
  const [isOpen, setOpen] = useState<boolean>(initial);

  const open = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen(v => !v), []);

  return { isOpen, open, close, toggle, setOpen };
}
