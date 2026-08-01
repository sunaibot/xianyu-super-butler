import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Search, CornerDownLeft, ArrowUp, ArrowDown } from 'lucide-react';
import { NAV_ITEMS } from './nav';
import type { TabId } from '../../contexts/NavigateContext';

export interface CommandAction {
  id: string;
  label: string;
  icon?: React.ElementType;
  hint?: string;
  run: () => void;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  setActiveTab: (tab: TabId) => void;
  actions?: CommandAction[];
}

/**
 * Command Palette（⌘K 快捷菜单）
 * - 快速跳转到任意页面
 * - 执行快捷操作（发布商品、同步订单等）
 * - 键盘导航：↑↓ 选择，Enter 执行，Esc 关闭
 */
const CommandPalette: React.FC<CommandPaletteProps> = ({ isOpen, onClose, setActiveTab, actions = [] }) => {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // 组合命令：跳转 + 动作
  const commands = useMemo(() => {
    const navCmds: CommandAction[] = NAV_ITEMS.map(item => ({
      id: `nav-${item.id}`,
      label: `跳转：${item.label}`,
      icon: item.icon,
      hint: '页面',
      run: () => {
        setActiveTab(item.id);
        onClose();
      },
    }));
    return [...navCmds, ...actions];
  }, [actions, setActiveTab, onClose]);

  const filtered = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter(c => c.label.toLowerCase().includes(q) || c.hint?.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setActiveIndex(0);
      // 延迟聚焦，等待 DOM 渲染
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex(i => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const cmd = filtered[activeIndex];
        if (cmd) cmd.run();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, filtered, activeIndex, onClose]);

  // 滚动激活项到可视区
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-idx="${activeIndex}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (!isOpen) return null;

  return createPortal(
    <div className="modal-overlay" onClick={onClose} style={{ alignItems: 'flex-start', paddingTop: '12vh' }}>
      <div
        className="modal-container animate-slide-up"
        style={{ maxWidth: '36rem', maxHeight: '70vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header" style={{ padding: '1rem 1.5rem' }}>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              ref={inputRef}
              type="text"
              aria-label="搜索命令"
              inputMode="search"
              placeholder="输入命令或页面名称…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActiveIndex(0);
              }}
              className="ios-input w-full pl-11 pr-4 py-3 rounded-xl text-sm h-12"
            />
          </div>
        </div>

        <div className="modal-body" ref={listRef} style={{ padding: '0.5rem' }}>
          {filtered.length === 0 ? (
            <div className="text-center text-sm text-gray-400 py-8">没有匹配的命令</div>
          ) : (
            filtered.map((cmd, idx) => {
              const Icon = cmd.icon;
              return (
                <button
                  key={cmd.id}
                  data-idx={idx}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={cmd.run}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors min-h-[44px] ${
                    idx === activeIndex ? 'bg-[#FFE815] text-black' : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {Icon && <Icon className="w-4 h-4 flex-shrink-0" />}
                  <span className="flex-1 text-sm font-medium">{cmd.label}</span>
                  {cmd.hint && (
                    <span className={`text-xs px-1.5 py-0.5 rounded ${idx === activeIndex ? 'bg-black/10' : 'bg-gray-100 text-gray-400'}`}>
                      {cmd.hint}
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>

        <div className="modal-footer" style={{ padding: '0.75rem 1.5rem' }}>
          <div className="flex items-center justify-between text-xs text-gray-400">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-gray-100 rounded inline-flex items-center"><ArrowUp className="w-3 h-3" /><ArrowDown className="w-3 h-3" /></kbd>
                选择
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-gray-100 rounded inline-flex items-center"><CornerDownLeft className="w-3 h-3" /></kbd>
                执行
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-gray-100 rounded">Esc</kbd>
                关闭
              </span>
            </div>
            <span>{filtered.length} 项</span>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

/** 全局 ⌘K / Ctrl+K 监听 hook */
export function useCommandPaletteHotkey(onToggle: () => void) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onToggle();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onToggle]);
}

export default CommandPalette;
