type RequestMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';

type QueryParams = Record<string, string | number | boolean | undefined | null>;

type JsonValue = unknown;

type RequestOptions = {
  params?: QueryParams;
  body?: JsonValue;
  /** 自定义请求头 */
  headers?: Record<string, string>;
  /** 超时毫秒数（默认 30s） */
  timeout?: number;
};

/** 默认超时 30 秒 */
const DEFAULT_TIMEOUT = 30_000;

const buildQueryString = (params?: QueryParams): string => {
  if (!params) return '';
  const searchParams = new URLSearchParams();
  for (const [key, rawVal] of Object.entries(params)) {
    if (rawVal === undefined || rawVal === null) continue;
    searchParams.set(key, String(rawVal));
  }
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
};

/**
 * 统一请求方法
 *
 * 支持：
 * - JSON / FormData body（FormData 时不设置 Content-Type，浏览器自动加 boundary）
 * - AbortController 超时控制
 * - 自定义 headers
 */
const request = async <T>(method: RequestMethod, url: string, options: RequestOptions = {}): Promise<T> => {
  const qs = buildQueryString(options.params);
  const fullUrl = `${url}${qs}`;

  // 构造 fetch options
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers: Record<string, string> = { ...(options.headers || {}) };
  let body: BodyInit | undefined;

  if (options.body === undefined) {
    body = undefined;
  } else if (isFormData) {
    // FormData：不设置 Content-Type，让浏览器自动添加 multipart boundary
    body = options.body as FormData;
  } else {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    body = JSON.stringify(options.body);
  }

  // 超时控制：AbortController
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), options.timeout ?? DEFAULT_TIMEOUT);

  let res: Response;
  try {
    res = await fetch(fullUrl, {
      method,
      credentials: 'include',
      headers,
      body,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('请求超时，请稍后重试');
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');

  if (!res.ok) {
    // 尽量返回后端的detail/message，避免吞错
    const payload = isJson ? await res.json().catch(() => undefined) : await res.text().catch(() => undefined);
    const detail = typeof payload === 'string' ? payload : (payload?.detail || payload?.message || payload?.msg);
    throw new Error(detail || `请求失败: ${res.status}`);
  }

  if (!isJson) {
    // 这里按现有后端习惯基本都会返回JSON；非JSON时直接返回text
    return (await res.text()) as unknown as T;
  }

  return (await res.json()) as T;
};

export const get = async <T>(url: string, params?: QueryParams, options?: Omit<RequestOptions, 'params' | 'body'>): Promise<T> =>
  request<T>('GET', url, { ...options, params });
export const post = async <T>(url: string, body?: JsonValue, options?: Omit<RequestOptions, 'body'>): Promise<T> =>
  request<T>('POST', url, { ...options, body });
export const put = async <T>(url: string, body?: JsonValue, options?: Omit<RequestOptions, 'body'>): Promise<T> =>
  request<T>('PUT', url, { ...options, body });
export const del = async <T>(url: string, params?: QueryParams, options?: Omit<RequestOptions, 'params' | 'body'>): Promise<T> =>
  request<T>('DELETE', url, { ...options, params });

/** 上传文件（FormData） */
export const upload = async <T>(url: string, formData: FormData, options?: Omit<RequestOptions, 'body'>): Promise<T> =>
  request<T>('POST', url, { ...options, body: formData });
