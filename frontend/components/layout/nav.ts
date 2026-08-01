import { LayoutDashboard, Users, ShoppingBag, CreditCard, Box, MessageSquare, BookOpen, Zap, Shield, Settings } from 'lucide-react';
import type { TabId } from '../../contexts/NavigateContext';

export interface NavItem {
  id: TabId;
  icon: typeof LayoutDashboard;
  label: string;
  /** 移动端是否在底部 TabBar（核心 5 项） */
  core?: boolean;
}

/** 全部导航项（桌面侧栏 / 移动端 TabBar / 抽屉共享） */
export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', icon: LayoutDashboard, label: '仪表盘', core: true },
  { id: 'orders', icon: ShoppingBag, label: '订单管理', core: true },
  { id: 'items', icon: Box, label: '商品列表', core: true },
  { id: 'cards', icon: CreditCard, label: '卡密库存', core: true },
  { id: 'accounts', icon: Users, label: '账号管理', core: true },
  { id: 'keywords', icon: MessageSquare, label: '关键词管理' },
  { id: 'kb', icon: BookOpen, label: '话术库' },
  { id: 'rules', icon: Zap, label: '智能策略' },
  { id: 'users', icon: Shield, label: '用户管理' },
  { id: 'settings', icon: Settings, label: '系统与AI' },
];

/** 移动端底部 TabBar 核心 5 项 */
export const CORE_NAV_ITEMS = NAV_ITEMS.filter(i => i.core);

/** 移动端抽屉"更多"项 */
export const MORE_NAV_ITEMS = NAV_ITEMS.filter(i => !i.core);

export const NAV_LABEL_MAP: Record<TabId, string> = NAV_ITEMS.reduce((acc, i) => {
  acc[i.id] = i.label;
  return acc;
}, {} as Record<TabId, string>);
