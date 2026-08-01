import React from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

export interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  total?: number;
  pageSize?: number;
  className?: string;
}

/**
 * 分页组件
 * 统一列表分页 UI，触摸优化按钮 ≥44px
 */
export const Pagination: React.FC<PaginationProps> = ({
  page,
  totalPages,
  onPageChange,
  total,
  pageSize,
  className = '',
}) => {
  if (totalPages <= 1) return null;

  // 生成页码：当前页 ±2，首尾，省略号
  const pages: (number | '...')[] = [];
  const add = (p: number | '...') => pages.push(p);
  add(1);
  if (page > 4) add('...');
  for (let i = Math.max(2, page - 2); i <= Math.min(totalPages - 1, page + 2); i++) {
    add(i);
  }
  if (page < totalPages - 3) add('...');
  if (totalPages > 1) add(totalPages);

  const btnBase = 'min-h-[40px] min-w-[40px] flex items-center justify-center rounded-xl text-sm font-semibold transition-colors';

  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 ${className}`}>
      {total != null && pageSize != null && (
        <div className="text-xs text-gray-500">
          共 {total} 条，每页 {pageSize} 条
        </div>
      )}
      <div className="flex items-center gap-1.5 ml-auto">
        <button
          onClick={() => onPageChange(1)}
          disabled={page <= 1}
          className={`${btnBase} text-gray-500 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed`}
          aria-label="首页"
        >
          <ChevronsLeft className="w-4 h-4" />
        </button>
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className={`${btnBase} text-gray-500 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed`}
          aria-label="上一页"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        {pages.map((p, i) =>
          p === '...' ? (
            <span key={`e${i}`} className="px-2 text-gray-400 text-sm">…</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className={`${btnBase} px-3 ${
                p === page
                  ? 'bg-[#FFE815] text-black'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className={`${btnBase} text-gray-500 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed`}
          aria-label="下一页"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        <button
          onClick={() => onPageChange(totalPages)}
          disabled={page >= totalPages}
          className={`${btnBase} text-gray-500 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed`}
          aria-label="末页"
        >
          <ChevronsRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default Pagination;
