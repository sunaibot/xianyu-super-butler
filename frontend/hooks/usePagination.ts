import { useState, useCallback } from 'react';

/**
 * 分页 Hook：统一 page/totalPages 逻辑
 * @param initialPage 初始页码
 * @param initialTotalPages 初始总页数
 *
 * @example
 * const { page, totalPages, setPage, next, prev } = usePagination(1, 1);
 * // setPage 支持直接传值或 functional updater：
 * setPage(2);
 * setPage(p => p + 1);
 */
export type SetPageFn = (p: number | ((prev: number) => number)) => void;

export interface UsePaginationReturn {
  page: number;
  totalPages: number;
  setPage: SetPageFn;
  setTotalPages: (t: number) => void;
  next: () => void;
  prev: () => void;
  canNext: boolean;
  canPrev: boolean;
  reset: () => void;
}

export function usePagination(initialPage: number = 1, initialTotalPages: number = 1): UsePaginationReturn {
  const [page, setPageState] = useState<number>(initialPage);
  const [totalPages, setTotalPages] = useState<number>(initialTotalPages);

  // 支持直接传值与 functional updater 两种形式（与 React 原生 setState 一致）
  const setPage = useCallback<SetPageFn>((p) => {
    setPageState(prev => {
      const next = typeof p === 'function' ? p(prev) : p;
      return Math.max(1, next);
    });
  }, []);

  const next = useCallback(() => {
    setPageState(p => Math.min(p + 1, totalPages));
  }, [totalPages]);

  const prev = useCallback(() => {
    setPageState(p => Math.max(1, p - 1));
  }, []);

  const reset = useCallback(() => {
    setPageState(1);
  }, []);

  return {
    page,
    totalPages,
    setPage,
    setTotalPages,
    next,
    prev,
    canNext: page < totalPages,
    canPrev: page > 1,
    reset,
  };
}
