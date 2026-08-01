import { useState, useEffect } from 'react';

/**
 * 防抖 Hook：对快速变化的值延迟更新
 * @param value 需要防抖的值
 * @param delay 延迟毫秒，默认 300ms
 * @returns 防抖后的值
 *
 * @example
 * const [text, setText] = useState('');
 * const debounced = useDebounce(text, 300);
 * useEffect(() => { searchAPI(debounced) }, [debounced]);
 */
export function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
