
// API Response Bases
export interface ApiResponse {
  success?: boolean;
  message?: string;
  msg?: string;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Auth
export interface LoginResponse {
  success: boolean;
  token?: string;
  message?: string;
  user_id?: number;
  username?: string;
  is_admin?: boolean;
}

// Accounts
export interface AccountDetail {
  id: string;
  value?: string; // cookie value from backend
  cookie?: string; // alias for value
  enabled: boolean;
  auto_confirm: boolean;
  remark?: string;
  note?: string; // alias for remark
  pause_duration?: number;
  // 登录信息
  username?: string;
  login_password?: string;
  show_browser?: boolean;
  // Frontend helpers
  nickname?: string;
  avatar_url?: string;
  // AI设置
  ai_enabled?: boolean;
  max_discount_percent?: number;
  max_discount_amount?: number;
  max_bargain_rounds?: number;
  custom_prompts?: string;
}

// Orders
export type OrderStatus = 
  | 'processing'      
  | 'pending_ship'    
  | 'shipped'         
  | 'completed'       
  | 'cancelled'       
  | 'refunding';

export interface Order {
  id: string;
  order_id: string;
  cookie_id: string;
  item_id: string;
  item_title?: string;
  item_image?: string;
  item_price?: string;
  buyer_id: string;
  quantity: number;
  amount: string;
  status: OrderStatus;
  order_status?: string;
  receiver_name?: string;
  receiver_phone?: string;
  receiver_address?: string;
  created_at?: string;
  updated_at?: string;
}

// Cards
export interface Card {
  id: number;
  name: string;
  type: 'api' | 'text' | 'data' | 'image';
  description?: string;
  enabled: boolean;
  // 文本类型
  text_content?: string;
  // 批量数据类型
  data_content?: string;
  // API 类型配置
  api_config?: {
    url: string;
    method: 'GET' | 'POST';
    timeout?: number;
    headers?: string;
    params?: string;
  };
  // 图片类型
  image_url?: string;
  // 通用配置
  delay_seconds?: number;
  // 多规格配置
  is_multi_spec?: boolean;
  spec_name?: string;
  spec_value?: string;
  // 编辑表单使用的扁平字段
  api_url?: string;
  api_method?: 'GET' | 'POST';
  api_timeout?: number;
  api_headers?: string;
  api_params?: string;
  created_at: string;
  updated_at: string;
}

// Items
export interface Item {
  id: string | number;
  cookie_id: string;
  item_id: string;
  item_title?: string;
  item_price?: string;
  item_image?: string;
  item_category?: string;
  is_multi_spec?: number | boolean;
  is_multi_qty_ship?: number | boolean;
  created_at?: string;
}

// Rules
export interface ShippingRule {
  id: string;
  name: string;
  item_keyword: string; // Matches item title
  card_group_id: number; // ID from Card list
  card_group_name?: string; // UI helper
  priority: number;
  enabled: boolean;
}

export interface ReplyRule {
  id: string;
  keyword: string;
  reply_content: string;
  match_type: 'exact' | 'fuzzy';
  enabled: boolean;
}

// Stats
export interface AdminStats {
  total_users: number;
  total_cookies: number;
  active_cookies: number;
  total_cards: number;
  total_keywords: number;
  total_orders: number;
  is_admin?: boolean;
}

export interface OrderAnalytics {
  revenue_stats: {
    total_amount: number;
    total_orders: number;
  };
  daily_stats: Array<{ date: string; amount: number; order_count?: number }>;
  item_stats?: Array<{
    item_id: string;
    order_count: number;
    total_amount: number;
    avg_amount: number;
  }>;
}

// Settings
export interface SystemSettings {
  ai_model?: string;
  ai_api_key?: string;
  ai_base_url?: string;
  default_reply?: string;
  registration_enabled?: boolean;
  smtp_server?: string;
  [key: string]: any;
}

export interface AIReplySettings {
  ai_enabled: boolean;
  model_name?: string;
  api_key?: string;
  base_url?: string;
  max_discount_percent: number;
  max_discount_amount?: number;
  max_bargain_rounds: number;
  custom_prompts: string;
}

// Default Reply
export interface DefaultReply {
  cookie_id: string;
  enabled: boolean;
  reply_content: string;
  reply_once: boolean;
  reply_image_url?: string;
}

// User Management
export interface UserInfo {
  id: number;
  username: string;
  email?: string;
  is_admin: boolean;
  created_at?: string;
  last_login?: string;
  status?: 'active' | 'disabled';
}

// Forbidden Words
export interface ForbiddenCheckResult {
  has_forbidden: boolean;
  found_words: string[];
  suggestions?: Record<string, string>;
  original_text?: string;
  cleaned_text?: string;
}

// Product Extraction
export interface ProductExtractionResult {
  success: boolean;
  product?: {
    title: string;
    price: string;
    images: string[];
    description: string;
    category: string;
  };
  message?: string;
}

// Product Publishing
export interface ProductPublishResult {
  success: boolean;
  message?: string;
  product_url?: string;
}

// Product Dedup
export interface ProductDedupResult {
  total_input: number;
  duplicate_count: number;
  unique_count: number;
  duplicates: Array<{
    index1: number;
    index2: number;
    similarity: number;
    reason: string;
  }>;
  unique_indices: number[];
}

// Performance Monitor
export interface PerformanceStats {
  today: {
    total_replies: number;
    ai_replies: number;
    kb_matches: number;
    avg_response_time: number;
    avg_ai_time: number;
    min_response_time: number;
    max_response_time: number;
  };
  summary: {
    total_replies: number;
    ai_replies: number;
    kb_matches: number;
    avg_response_time: number;
    min_response_time: number;
    max_response_time: number;
  };
  recent: Array<{
    timestamp: string;
    intent: string;
    source: string;
    response_time: number;
  }>;
  provider_comparison?: Record<string, {
    count: number;
    avg_time: number;
  }>;
}
