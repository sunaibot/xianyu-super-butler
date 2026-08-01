import { useState, useEffect } from 'react';

/**
 * 响应式媒体查询 Hook
 * @param query CSS 媒体查询字符串，默认检测移动端 (max-width: 768px)
 * @returns 是否匹配
 *
 * @example
 * const isMobile = useMediaQuery(); // 默认 max-width: 768px
 * const isTablet = useMediaQuery('(min-width: 769px) and (max-width: 1024px)');
 */
export function useMediaQuery(query: string = '(max-width: 768px)'): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    // 初始化同步一次，避免 SSR 不一致
    setMatches(mql.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

/** 便捷预设：是否为移动端（≤768px） */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 768px)');
}

/** 便捷预设：是否为桌面端（≥769px） */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 769px)');
}
