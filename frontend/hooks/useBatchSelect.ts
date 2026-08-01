import { useState, useCallback, useMemo } from 'react';

/**
 * 列表批量选择 Hook
 * @param allIds 全部可选 id 列表（用于全选判断）
 * @returns { selectedIds, isSelected, toggle, selectAll, clear, toggleAll, count }
 *
 * @example
 * const { selectedIds, toggle, selectAll, clear } = useBatchSelect<string>(allIds);
 */
export interface UseBatchSelectReturn<T> {
  selectedIds: T[];
  selectedSet: Set<T>;
  isSelected: (id: T) => boolean;
  toggle: (id: T) => void;
  selectAll: () => void;
  clear: () => void;
  toggleAll: () => void;
  isAllSelected: boolean;
  isIndeterminate: boolean;
  count: number;
}

export function useBatchSelect<T = string | number>(allIds: T[] = []): UseBatchSelectReturn<T> {
  const [selectedSet, setSelectedSet] = useState<Set<T>>(new Set());

  const isSelected = useCallback((id: T) => selectedSet.has(id), [selectedSet]);

  const toggle = useCallback((id: T) => {
    setSelectedSet(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedSet(new Set(allIds));
  }, [allIds]);

  const clear = useCallback(() => {
    setSelectedSet(new Set());
  }, []);

  const toggleAll = useCallback(() => {
    setSelectedSet(prev => {
      if (prev.size === allIds.length && allIds.every(id => prev.has(id))) {
        return new Set();
      }
      return new Set(allIds);
    });
  }, [allIds]);

  const selectedIds = useMemo(() => Array.from(selectedSet), [selectedSet]);

  const isAllSelected = allIds.length > 0 && selectedSet.size === allIds.length && allIds.every(id => selectedSet.has(id));
  const isIndeterminate = selectedSet.size > 0 && !isAllSelected;

  return {
    selectedIds,
    selectedSet,
    isSelected,
    toggle,
    selectAll,
    clear,
    toggleAll,
    isAllSelected,
    isIndeterminate,
    count: selectedSet.size,
  };
}
