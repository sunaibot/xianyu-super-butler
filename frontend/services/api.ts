import { get, post, put, del } from '../request';
import {
  LoginResponse, AccountDetail, Order, PaginatedResponse,
  AdminStats, Card, SystemSettings, ApiResponse, OrderAnalytics,
  Item, AIReplySettings, ShippingRule, ReplyRule, DefaultReply, UserInfo,
  ForbiddenCheckResult, ProductExtractionResult, ProductPublishResult,
  ProductDedupResult, PerformanceStats
} from '../types';

// Auth
export const login = async (data: { username?: string; password?: string; email?: string; verification_code?: string }): Promise<LoginResponse> => {
  return post('/login', data);
};

export const verifySession = async (): Promise<{ authenticated: boolean; initialized?: boolean; user_id?: number; username?: string; is_admin?: boolean }> => {
  return get('/verify');
};

// Accounts
export const getAccountDetails = async (): Promise<AccountDetail[]> => {
  const data = await get<any[]>('/cookies/details');
  return data.map(item => ({
    id: item.id,
    value: '',
    cookie: '',
    enabled: item.enabled,
    auto_confirm: item.auto_confirm,
    remark: item.remark,
    note: item.remark,
    pause_duration: item.pause_duration,
    username: item.username || '',
    login_password: '',
    show_browser: item.show_browser,
    nickname: item.remark || `Account ${item.id.substring(0,6)}`,
    avatar_url: `https://api.dicebear.com/7.x/avataaars/svg?seed=${item.id}`,
    ai_enabled: false,
  }));
};

export const getAccountForEdit = async (id: string): Promise<Partial<AccountDetail> & { id: string; value?: string }> => {
  return get(`/cookie/${id}/details?include_value=true`);
};

export const generateQRLogin = async (): Promise<{ success: boolean; session_id?: string; qr_code_url?: string }> => {
  return post('/qr-login/generate');
};

export interface QRLoginStatusResult {
  success: boolean;
  // 后端可能返回的状态：pending/processing/success/already_processed/expired/cancelled/verification_required/error/failed
  status: 'pending' | 'processing' | 'success' | 'already_processed' | 'expired' | 'cancelled' | 'verification_required' | 'error' | 'failed';
  cookie_id?: string;
  message?: string;
}

export const checkQRLoginStatus = async (sessionId: string): Promise<QRLoginStatusResult> => {
  return get(`/qr-login/check/${sessionId}`);
};

export const updateAccountStatus = async (id: string, enabled: boolean): Promise<ApiResponse> => {
  return put(`/cookies/${id}/status`, { enabled });
};

export const deleteAccount = async (id: string): Promise<ApiResponse> => {
  return del(`/cookies/${id}`);
};

export const updateAccountRemark = async (id: string, remark: string): Promise<ApiResponse> => {
  return put(`/cookies/${id}/remark`, { remark });
};

export const updateAccountAutoConfirm = async (id: string, autoConfirm: boolean): Promise<ApiResponse> => {
  return put(`/cookies/${id}/auto-confirm`, { auto_confirm: autoConfirm });
};

export const updateAccountPauseDuration = async (id: string, pauseDuration: number): Promise<ApiResponse> => {
  return put(`/cookies/${id}/pause-duration`, { pause_duration: pauseDuration });
};

export const updateAccountCookie = async (id: string, value: string): Promise<ApiResponse> => {
  return put(`/cookies/${id}`, { id, value });
};

export const updateAccountLoginInfo = async (id: string, data: {
  username?: string;
  login_password?: string;
  show_browser?: boolean;
}): Promise<ApiResponse> => {
  return put(`/cookies/${id}/login-info`, data);
};

export const getAllAISettings = async (): Promise<Record<string, AIReplySettings>> => {
  return get('/ai-reply-settings');
};

// Knowledge Base
export interface KBScript {
  id: number;
  user_question: string;
  answer: string;
  intent_l1?: string;
  intent_l2?: string;
  created_at?: string;
}

export interface KBScriptsResponse {
  // 后端 /kb/scripts 返回 scripts + total + page + page_size（无 success/total_pages）
  scripts: KBScript[];
  total: number;
  page: number;
  page_size: number;
  total_pages?: number; // 后端未返回，前端按 total/page_size 计算
}

export interface KBStatus {
  total_scripts: number;
  search_mode?: string;
}

export interface KBSearchResult {
  results: Array<{
    id: number;
    document: string;
    similarity: number;
    metadata: {
      answer: string;
      intent_l1?: string;
      intent_l2?: string;
    };
  }>;
}

export const getKBScripts = async (page: number = 1, pageSize: number = 20, search: string = ''): Promise<KBScriptsResponse> => {
  const params: Record<string, string | number | boolean> = { page, page_size: pageSize };
  if (search) params.search = search;
  return get('/kb/scripts', params);
};

export const createKBScript = async (data: { user_question: string; answer: string; intent_l1?: string; intent_l2?: string }): Promise<{ id: number } & ApiResponse> => {
  return post('/kb/scripts', data);
};

export const updateKBScript = async (id: number, data: { user_question: string; answer: string; intent_l1?: string; intent_l2?: string }): Promise<ApiResponse> => {
  return put(`/kb/scripts/${id}`, data);
};

export const deleteKBScript = async (id: number): Promise<ApiResponse> => {
  return del(`/kb/scripts/${id}`);
};

export const rebuildKBIndex = async (): Promise<ApiResponse> => {
  return post('/kb/rebuild', {});
};

export const getKBStatus = async (): Promise<KBStatus> => {
  return get('/kb/status');
};

export const searchKB = async (query: string, nResults: number = 3): Promise<KBSearchResult> => {
  return post('/kb/search', { query, n_results: nResults });
};

export const importKBCSV = async (csvContent: string): Promise<{ imported: number } & ApiResponse> => {
  return post('/kb/import', { csv_content: csvContent });
};

// Orders
export const getOrders = async (
  cookieId?: string,
  status?: string,
  page: number = 1,
  pageSize: number = 20,
  search?: string
): Promise<PaginatedResponse<Order>> => {
  const params: Record<string, string | number | boolean> = { page, page_size: pageSize };
  if (cookieId) params.cookie_id = cookieId;
  if (status && status !== 'all') params.status = status;
  if (search) params.search = search;

  const res = await get<PaginatedResponse<Order>>('/api/orders', params);

  // Handle backend response variations
  // 后端统一返回 PaginatedResponse 结构（data/total/page/page_size/total_pages）
  const orders = res.data || [];
  return {
    success: true,
    data: orders,
    total: res.total ?? orders.length,
    page: res.page ?? page,
    page_size: res.page_size ?? pageSize,
    total_pages: res.total_pages ?? 1
  };
};

export const updateOrder = async (orderId: string, data: Partial<Order>): Promise<ApiResponse> => {
  return put(`/api/orders/${orderId}`, data);
};

export const deleteOrder = async (orderId: string): Promise<ApiResponse> => {
  return del(`/api/orders/${orderId}`);
};

export const syncOrders = async (cookieId?: string, status?: string): Promise<{ success: boolean; synced?: number; message?: string }> => {
  const formData = new FormData();
  if (cookieId) formData.append('cookie_id', cookieId);
  if (status) formData.append('status', status);

  // 使用 fetch 来发送 FormData（Cookie 会话，自动携带凭证）
  const response = await fetch('/api/orders/refresh', {
    method: 'POST',
    credentials: 'include',
    body: formData
  });
  return response.json();
};

export const syncSingleOrder = async (orderId: string): Promise<{ success: boolean; order?: Order; message?: string }> => {
  return post(`/api/orders/${orderId}/refresh`);
};

export interface ManualShipResult {
  order_id: string;
  success: boolean;
  message: string;
}

export const manualShipOrder = async (orderIds: string[], shipMode: 'status_only' | 'full_delivery', content?: string): Promise<{
  success: boolean;
  message: string;
  success_count: number;
  failed_count: number;
  results: ManualShipResult[];
}> => {
    return post('/api/orders/manual-ship', {
        order_ids: orderIds,
        ship_mode: shipMode,
        custom_content: content
    });
}

export interface ImportOrderResult {
  order_id: string;
  success: boolean;
  message: string;
}

export const importOrders = async (data: Partial<Order>[] | FormData): Promise<{
  success: boolean;
  message: string;
  success_count: number;
  failed_count: number;
  results: ImportOrderResult[];
}> => {
  const isFormData = data instanceof FormData;
  const response = await fetch('/api/orders/import', {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    },
    body: isFormData ? data : JSON.stringify(data)
  });
  return response.json();
}

// Stats
export const getAdminStats = async (): Promise<AdminStats> => {
  return get('/api/stats');
};

export const getOrderAnalytics = async (daysOrParams: number | {start_date: string; end_date: string} = 7): Promise<OrderAnalytics> => {
    let params: {start_date: string; end_date: string};

    if (typeof daysOrParams === 'number') {
        const endDate = new Date();
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - daysOrParams);
        params = {
            start_date: startDate.toISOString().split('T')[0],
            end_date: endDate.toISOString().split('T')[0]
        };
    } else {
        params = daysOrParams;
    }

    return get('/analytics/orders', params);
}

export const getValidOrders = async (dateRange: {start_date: string; end_date: string}): Promise<Order[]> => {
    const res = await get<{ orders?: Order[] } & ApiResponse>('/analytics/orders/valid', {
        start_date: dateRange.start_date,
        end_date: dateRange.end_date
    });
    return res.orders || [];
}

// Cards
export const getCards = async (): Promise<Card[]> => {
  const res = await get<Card[] | { cards?: Card[] }>('/cards');
  return Array.isArray(res) ? res : (res.cards || []);
};

export const createCard = async (data: Partial<Card>): Promise<{ id: number; message: string }> => {
  return post('/cards', data);
};

export const updateCard = async (cardId: number, data: Partial<Card>): Promise<ApiResponse> => {
  return put(`/cards/${cardId}`, data);
};

export const deleteCard = async (cardId: number): Promise<ApiResponse> => {
  return del(`/cards/${cardId}`);
};

// Items
export const getItems = async (): Promise<Item[]> => {
    const res = await get<Item[] | { items?: Item[] }>('/items');
    return Array.isArray(res) ? res : (res.items || []);
}

export const syncItemsFromAccount = async (cookieId: string): Promise<{ success: boolean; synced?: number; message?: string }> => {
    return post('/items/get-all-from-account', { cookie_id: cookieId });
}

export const deleteItem = async (cookieId: string, itemId: string): Promise<ApiResponse> => {
    return del(`/items/${cookieId}/${itemId}`);
}

export const createItem = async (cookieId: string, data: Partial<Item>): Promise<ApiResponse> => {
    return post(`/items/${cookieId}`, data);
}

export const updateItem = async (cookieId: string, itemId: string, data: Partial<Item>): Promise<ApiResponse> => {
    return put(`/items/${cookieId}/${itemId}`, data);
}

export const updateItemMultiSpec = async (cookieId: string, itemId: string, isMultiSpec: boolean): Promise<ApiResponse> => {
    return put(`/items/${cookieId}/${itemId}/multi-spec`, { is_multi_spec: isMultiSpec });
}

export const updateItemMultiQty = async (cookieId: string, itemId: string, isMultiQty: boolean): Promise<ApiResponse> => {
    return put(`/items/${cookieId}/${itemId}/multi-quantity-delivery`, { multi_quantity_delivery: isMultiQty });
}

// Rules - 发货规则 (使用正确的后端API)
interface BackendShippingRule {
    id: number | string;
    keyword?: string;
    description?: string;
    card_id?: number;
    card_name?: string;
    delivery_count?: number;
    enabled?: boolean;
}

export const getShippingRules = async (): Promise<ShippingRule[]> => {
    const res = await get<BackendShippingRule[] | { data?: BackendShippingRule[]; rules?: BackendShippingRule[] }>('/delivery-rules');
    const rules = Array.isArray(res) ? res : (res.data || res.rules || []);
    // 转换后端数据格式到前端格式
    return rules.map((item: BackendShippingRule) => ({
        id: String(item.id),
        name: item.description || item.keyword || '',
        item_keyword: item.keyword || '',
        card_group_id: item.card_id || 0,
        card_group_name: item.card_name || '',
        priority: item.delivery_count || 1,
        enabled: item.enabled || false
    }));
}

export const updateShippingRule = async (rule: Partial<ShippingRule>): Promise<ApiResponse> => {
    const payload = {
        keyword: rule.item_keyword,
        card_id: rule.card_group_id,
        delivery_count: rule.priority,
        enabled: rule.enabled ?? true,
        description: rule.name
    };
    return rule.id ? put(`/delivery-rules/${rule.id}`, payload) : post('/delivery-rules', payload);
}

export const deleteShippingRule = async (id: string): Promise<ApiResponse> => del(`/delivery-rules/${id}`);

// Rules - 关键词回复规则 (使用关键词API)
interface BackendKeyword {
    keyword: string;
    reply: string;
    item_id?: string;
}

export const getReplyRules = async (cookieId?: string): Promise<ReplyRule[]> => {
    if (!cookieId) return [];
    const res = await get<BackendKeyword[] | { data?: BackendKeyword[] }>(`/keywords-with-item-id/${cookieId}`);
    const keywords = Array.isArray(res) ? res : [];
    return keywords.map((item: BackendKeyword, index: number) => ({
        id: String(index),
        keyword: item.keyword || '',
        reply_content: item.reply || '',
        match_type: 'exact' as const,
        enabled: true
    }));
}

export const updateReplyRule = async (rule: Partial<ReplyRule>, cookieId: string): Promise<ApiResponse> => {
    // 获取现有关键词
    const existing = await get<BackendKeyword[]>(`/keywords-with-item-id/${cookieId}`);
    const keywords = Array.isArray(existing) ? existing : [];

    // 更新或添加关键词
    if (rule.id) {
        const index = parseInt(rule.id);
        if (index >= 0 && index < keywords.length) {
            keywords[index] = {
                keyword: rule.keyword || '',
                reply: rule.reply_content || '',
                item_id: ''
            };
        }
    } else {
        keywords.push({
            keyword: rule.keyword || '',
            reply: rule.reply_content || '',
            item_id: ''
        });
    }

    return post(`/keywords-with-item-id/${cookieId}`, { keywords });
}

export const deleteReplyRule = async (id: string, cookieId: string): Promise<ApiResponse> => {
    const existing = await get<BackendKeyword[]>(`/keywords-with-item-id/${cookieId}`);
    const keywords = Array.isArray(existing) ? existing : [];
    const index = parseInt(id);
    if (index >= 0 && index < keywords.length) {
        keywords.splice(index, 1);
    }
    return post(`/keywords-with-item-id/${cookieId}`, { keywords });
}

// Settings
export const getSystemSettings = async (): Promise<SystemSettings> => {
    const res = await get<{data: SystemSettings}>('/system-settings');
    return res.data || res; // handle {success:true, data: {...}} wrapper if exists
};

export const updateSystemSettings = async (settings: Partial<SystemSettings>): Promise<ApiResponse> => {
    // Use sequential updates instead of concurrent to avoid data consistency issues
    const entries = Object.entries(settings);
    for (const [key, value] of entries) {
        await put(`/system-settings/${key}`, { value: String(value) });
    }
    return { success: true, message: 'Settings saved' };
};

export const testWebhook = async (data: { url: string; secret?: string; event_type?: string; data?: any }): Promise<{ success: boolean; status_code: number; response: string }> => {
    return post('/webhook/test', data);
};

export const getAccountAISettings = async (cookieId: string): Promise<AIReplySettings> => {
    return get(`/ai-reply-settings/${cookieId}`);
}

export const updateAccountAISettings = async (cookieId: string, settings: Partial<AIReplySettings>): Promise<ApiResponse> => {
  const payload = {
    ai_enabled: settings.ai_enabled ?? false,
    model_name: settings.model_name ?? 'qwen-plus',
    api_key: settings.api_key ?? '',
    base_url: settings.base_url ?? 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    max_discount_percent: settings.max_discount_percent ?? 10,
    max_discount_amount: settings.max_discount_amount ?? 100,
    max_bargain_rounds: settings.max_bargain_rounds ?? 3,
    custom_prompts: settings.custom_prompts ?? ''
  };
  return put(`/ai-reply-settings/${cookieId}`, payload);
}

export const testAIConnection = async (cookieId: string): Promise<ApiResponse> => {
  const result = await post<{ success?: boolean; message?: string; reply?: string }>(`/ai-reply-test/${cookieId}`, {
    message: '你好，这是一条测试消息',
  });
  if (result.reply) {
    return { success: true, message: `AI 回复: ${result.reply}` };
  }
  return { success: result.success ?? true, message: result.message || 'AI 连接测试成功' };
}

// Default Reply
export const getDefaultReplies = async (): Promise<Record<string, DefaultReply>> => {
  return get('/api/default-replies');
};

export const getDefaultReply = async (cookieId: string): Promise<DefaultReply> => {
  const result = await get<Partial<DefaultReply>>(`/api/default-reply/${cookieId}`);
  return {
    cookie_id: cookieId,
    enabled: result.enabled || false,
    reply_content: result.reply_content || '',
    reply_once: result.reply_once || false,
    reply_image_url: result.reply_image_url || ''
  };
};

export const updateDefaultReply = async (cookieId: string, data: Partial<DefaultReply>): Promise<ApiResponse> => {
  return put(`/api/default-reply/${cookieId}`, {
    enabled: data.enabled ?? false,
    reply_content: data.reply_content || '',
    reply_once: data.reply_once ?? false,
    reply_image_url: data.reply_image_url || ''
  });
};

export const deleteDefaultReply = async (cookieId: string): Promise<ApiResponse> => {
  return del(`/api/default-reply/${cookieId}`);
};

export const clearDefaultReplyRecords = async (cookieId: string): Promise<ApiResponse> => {
  return post(`/api/default-reply/${cookieId}/clear-records`, {});
};

// User Management (Admin only)
export const getAllUsers = async (): Promise<UserInfo[]> => {
  const res = await get<UserInfo[] | { users?: UserInfo[]; data?: UserInfo[] }>('/admin/users');
  return Array.isArray(res) ? res : (res.users || res.data || []);
};

export const deleteUser = async (userId: number): Promise<ApiResponse> => {
  return del(`/admin/users/${userId}`);
};

export const changeAdminPassword = async (currentPassword: string, newPassword: string): Promise<ApiResponse> => {
  return post('/change-admin-password', { current_password: currentPassword, new_password: newPassword });
};

// Services - Forbidden Words
export const checkForbiddenWords = async (text: string): Promise<ForbiddenCheckResult> => {
  return post('/api/services/forbidden-check', { text });
};

export const cleanForbiddenWords = async (text: string): Promise<ForbiddenCheckResult> => {
  return post('/api/services/forbidden-clean', { text });
};

// Services - Product Extraction
export const extractProduct = async (productUrl: string): Promise<ProductExtractionResult> => {
  return post('/api/services/extract-product', { product_url: productUrl });
};

// Services - Product Publishing
export const publishProduct = async (data: {
  title: string;
  price: string;
  description?: string;
  images?: string[];
  category?: string;
}): Promise<ProductPublishResult> => {
  return post('/api/services/publish-product', data);
};

// Services - Product Dedup
export const dedupProducts = async (data: {
  item_urls?: string[];
  item_titles?: string[];
  item_descriptions?: string[];
}): Promise<ProductDedupResult> => {
  return post('/api/services/product-dedup', data);
};

// Services - Performance Monitor
export const getPerformanceStats = async (): Promise<PerformanceStats> => {
  return get('/api/services/performance-stats');
};

export const resetPerformanceStats = async (): Promise<ApiResponse> => {
  return post('/api/services/performance-reset', {});
};