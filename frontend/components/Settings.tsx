import React, { useEffect, useState } from 'react';
import { getSystemSettings, updateSystemSettings, testWebhook } from '../services/api';
import { SystemSettings } from '../types';
import {
  Bot, Save, Lock, Sparkles, Mail, Settings as SettingsIcon,
  Eye, EyeOff, RefreshCw, Database, ToggleLeft, ToggleRight, CheckCircle,
  Webhook, Send, Zap
} from 'lucide-react';

interface Toast {
  id: number;
  type: 'success' | 'error';
  message: string;
}

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [testingWebhook, setTestingWebhook] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Password visibility states
  const [showApiKey, setShowApiKey] = useState(false);
  const [showSmtpPassword, setShowSmtpPassword] = useState(false);

  const showToast = (type: 'success' | 'error', message: string) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000);
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = () => {
    setLoading(true);
    getSystemSettings().then(setSettings).finally(() => setLoading(false));
  };

  const handleSave = async () => {
      if(!settings) return;
      setSaving(true);
      try {
        await updateSystemSettings(settings);
        showToast('success', '系统配置已保存');
      } catch (e) {
        showToast('error', '保存失败：' + (e as Error).message);
      } finally {
        setSaving(false);
      }
  };

  const handleTestWebhook = async () => {
      if (!settings) return;
      setTestingWebhook(true);
      setTestResult(null);
      try {
        const result = await testWebhook({
          url: settings.webhook_url || '',
          secret: settings.webhook_secret || '',
          event_type: 'test_event',
          data: { message: '这是一条来自闲鱼自动发货系统的测试消息', test: true }
        });
        setTestResult({
          success: result.success,
          message: result.success
            ? `测试成功！Webhook 响应状态码: ${result.status_code}`
            : `测试失败: HTTP ${result.status_code} - ${result.response?.substring(0, 200) || '无响应'}`
        });
        showToast(result.success ? 'success' : 'error', result.success ? 'Webhook 测试成功' : 'Webhook 测试失败');
      } catch (e) {
        setTestResult({ success: false, message: (e as Error).message });
        showToast('error', '测试失败: ' + (e as Error).message);
      } finally {
        setTestingWebhook(false);
      }
  };

  const toggleWebhookEvent = (eventType: string) => {
      if (!settings) return;
      const currentEvents = (settings.webhook_events || '').split(',').filter((e: string) => e.trim());
      const updated = currentEvents.includes(eventType)
        ? currentEvents.filter((e: string) => e !== eventType)
        : [...currentEvents, eventType];
      setSettings({ ...settings, webhook_events: updated.join(',') });
  };

  if (!settings) return <div className="p-8 text-center text-gray-400">加载配置中...</div>;

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-fade-in pb-24">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center">
              <SettingsIcon className="w-6 h-6 text-gray-600" />
          </div>
          <div>
              <h2 className="text-3xl font-extrabold text-gray-900">系统设置</h2>
              <p className="text-gray-500 mt-1 text-sm font-medium">配置全局自动化规则与系统参数</p>
          </div>
        </div>
        <button
          onClick={loadSettings}
          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-xl font-bold text-gray-700 flex items-center gap-2 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left Column */}
        <div className="space-y-8">
          {/* Basic Settings */}
          <section className="space-y-4">
            <h3 className="text-lg font-extrabold text-gray-800 flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-gray-100 text-gray-600">
                    <Database className="w-4 h-4" />
                </div>
                基础设置
            </h3>

            <div className="ios-card rounded-[2rem] p-6 bg-white space-y-4">
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                <div>
                  <div className="font-bold text-gray-900">允许用户注册</div>
                  <div className="text-xs text-gray-500 mt-1">开启后允许新用户注册账号</div>
                </div>
                <button
                  onClick={() => setSettings({...settings, registration_enabled: !settings.registration_enabled})}
                  className={`w-14 h-8 rounded-full transition-all relative ${
                    settings.registration_enabled ? 'bg-[#FFE815]' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`w-6 h-6 bg-white rounded-full absolute top-1 transition-all shadow-md ${
                      settings.registration_enabled ? 'left-7' : 'left-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                <div>
                  <div className="font-bold text-gray-900">显示默认登录信息</div>
                  <div className="text-xs text-gray-500 mt-1">登录页面显示默认账号密码提示</div>
                </div>
                <button
                  onClick={() => setSettings({...settings, show_default_login_info: !settings.show_default_login_info})}
                  className={`w-14 h-8 rounded-full transition-all relative ${
                    settings.show_default_login_info ? 'bg-[#FFE815]' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`w-6 h-6 bg-white rounded-full absolute top-1 transition-all shadow-md ${
                      settings.show_default_login_info ? 'left-7' : 'left-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                <div>
                  <div className="font-bold text-gray-900">登录滑动验证码</div>
                  <div className="text-xs text-gray-500 mt-1">开启后账号密码登录需要完成滑动验证</div>
                </div>
                <button
                  onClick={() => setSettings({...settings, login_captcha_enabled: !settings.login_captcha_enabled})}
                  className={`w-14 h-8 rounded-full transition-all relative ${
                    settings.login_captcha_enabled ? 'bg-[#FFE815]' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`w-6 h-6 bg-white rounded-full absolute top-1 transition-all shadow-md ${
                      settings.login_captcha_enabled ? 'left-7' : 'left-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                <div>
                  <div className="font-bold text-gray-900">启用商品自动同步</div>
                  <div className="text-xs text-gray-500 mt-1">定时自动获取商品信息到本地数据库</div>
                </div>
                <button
                  onClick={() => setSettings({...settings, item_sync_enabled: !settings.item_sync_enabled})}
                  className={`w-14 h-8 rounded-full transition-all relative ${
                    settings.item_sync_enabled ? 'bg-[#FFE815]' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`w-6 h-6 bg-white rounded-full absolute top-1 transition-all shadow-md ${
                      settings.item_sync_enabled ? 'left-7' : 'left-1'
                    }`}
                  />
                </button>
              </div>

              <div className="space-y-3 px-4">
                <label className="block text-sm font-bold text-gray-800">商品同步间隔（分钟）</label>
                <input
                  type="number"
                  value={Math.round((settings.item_sync_interval || 600) / 60)}
                  onChange={(e) => {
                    const minutes = parseInt(e.target.value) || 10;
                    setSettings({...settings, item_sync_interval: minutes * 60});
                  }}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                  min="1"
                  max="1440"
                />
                <p className="text-xs text-gray-500">建议：10-60分钟</p>
              </div>

              <div className="space-y-3 px-4">
                <label className="block text-sm font-bold text-gray-800">每次最多同步页数</label>
                <input
                  type="number"
                  value={settings.item_sync_max_pages || 5}
                  onChange={(e) => setSettings({...settings, item_sync_max_pages: parseInt(e.target.value) || 5})}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                  min="1"
                  max="50"
                />
                <p className="text-xs text-gray-500">每页20个商品</p>
              </div>
            </div>
          </section>

          {/* AI Configuration */}
          <section className="space-y-4">
            <h3 className="text-lg font-extrabold text-gray-800 flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-[#FFE815] text-black">
                    <Sparkles className="w-4 h-4" />
                </div>
                AI 智能回复配置
            </h3>

            <div className="ios-card rounded-[2rem] p-6 bg-white space-y-6">
              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">API 地址</label>
                <input
                  type="text"
                  value={settings.ai_api_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1'}
                  onChange={e => setSettings({...settings, ai_api_url: e.target.value})}
                  className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                  placeholder="https://api.openai.com/v1"
                />
                <p className="text-xs text-gray-500">无需补全 /chat/completions</p>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">API Key</label>
                <div className="relative">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={settings.ai_api_key || ''}
                    onChange={e => setSettings({...settings, ai_api_key: e.target.value})}
                    className="w-full ios-input px-4 py-3 pr-12 rounded-xl font-mono text-sm"
                    placeholder="sk-..."
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-2 text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">模型</label>
                <select
                  value={settings.ai_model || 'qwen-plus'}
                  onChange={e => setSettings({...settings, ai_model: e.target.value})}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                >
                  <option value="qwen-plus">通义千问 Plus</option>
                  <option value="qwen-turbo">通义千问 Turbo</option>
                  <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                  <option value="gpt-4">GPT-4</option>
                </select>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">默认自动回复内容</label>
                <textarea
                  className="w-full ios-input px-4 py-3 rounded-xl min-h-[100px] text-sm resize-none"
                  value={settings.default_reply || ''}
                  onChange={e => setSettings({...settings, default_reply: e.target.value})}
                  placeholder="设置默认的自动回复内容..."
                ></textarea>
              </div>

              <div className="p-3 bg-amber-50 rounded-xl text-xs text-amber-700">
                <strong>常见 AI 服务:</strong>
                <ul className="list-disc list-inside mt-1 space-y-0.5">
                  <li>阿里云通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1</li>
                  <li>OpenAI: https://api.openai.com/v1</li>
                </ul>
              </div>
            </div>
          </section>
        </div>

        {/* Right Column */}
        <div className="space-y-8">
          {/* SMTP Settings */}
          <section className="space-y-4">
            <h3 className="text-lg font-extrabold text-gray-800 flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-blue-100 text-blue-600">
                    <Mail className="w-4 h-4" />
                </div>
                SMTP 邮件配置
            </h3>

            <div className="ios-card rounded-[2rem] p-6 bg-white space-y-6">
              <p className="text-sm text-gray-500">配置SMTP服务器用于发送注册验证码等邮件通知</p>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-3">
                  <label className="block text-sm font-bold text-gray-800">SMTP服务器</label>
                  <input
                    type="text"
                    value={settings.smtp_server || ''}
                    onChange={e => setSettings({...settings, smtp_server: e.target.value})}
                    placeholder="smtp.qq.com"
                    className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                  />
                </div>
                <div className="space-y-3">
                  <label className="block text-sm font-bold text-gray-800">SMTP端口</label>
                  <input
                    type="number"
                    value={settings.smtp_port || 587}
                    onChange={e => setSettings({...settings, smtp_port: parseInt(e.target.value)})}
                    placeholder="587"
                    className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                  />
                </div>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">发件邮箱</label>
                <input
                  type="email"
                  value={settings.smtp_user || ''}
                  onChange={e => setSettings({...settings, smtp_user: e.target.value})}
                  placeholder="your-email@qq.com"
                  className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                />
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">邮箱密码/授权码</label>
                <div className="relative">
                  <input
                    type={showSmtpPassword ? 'text' : 'password'}
                    value={settings.smtp_password || ''}
                    onChange={e => setSettings({...settings, smtp_password: e.target.value})}
                    placeholder="输入密码或授权码"
                    className="w-full ios-input px-4 py-3 pr-12 rounded-xl text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowSmtpPassword(!showSmtpPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-2 text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    {showSmtpPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-gray-500">QQ邮箱需要使用授权码</p>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">发件人显示名（可选）</label>
                <input
                  type="text"
                  value={settings.smtp_from || ''}
                  onChange={e => setSettings({...settings, smtp_from: e.target.value})}
                  placeholder="闲鱼自动回复系统"
                  className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                />
              </div>
            </div>
          </section>

          {/* Webhook 配置 */}
          <section className="space-y-4">
            <h3 className="text-lg font-extrabold text-gray-800 flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-green-100 text-green-600">
                    <Webhook className="w-4 h-4" />
                </div>
                Webhook 通知配置
            </h3>

            <div className="ios-card rounded-[2rem] p-6 bg-white space-y-6">
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                <div>
                  <div className="font-bold text-gray-900 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-500" />
                    启用 Webhook 推送
                  </div>
                  <div className="text-xs text-gray-500 mt-1">将系统事件实时推送到指定 Webhook URL（支持 n8n、企业微信、钉钉等）</div>
                </div>
                <button
                  onClick={() => setSettings({...settings, webhook_enabled: !settings.webhook_enabled})}
                  className={`w-14 h-8 rounded-full transition-all relative ${
                    settings.webhook_enabled ? 'bg-[#FFE815]' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`w-6 h-6 bg-white rounded-full absolute top-1 transition-all shadow-md ${
                      settings.webhook_enabled ? 'left-7' : 'left-1'
                    }`}
                  />
                </button>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">Webhook URL</label>
                <input
                  type="url"
                  value={settings.webhook_url || ''}
                  onChange={e => setSettings({...settings, webhook_url: e.target.value})}
                  placeholder="https://your-n8n.example.com/webhook/xxx"
                  className="w-full ios-input px-4 py-3 rounded-xl text-sm font-mono"
                />
                <p className="text-xs text-gray-500">支持 n8n / 企业微信机器人 / 钉钉机器人 / 飞书机器人等 Webhook 地址</p>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">签名密钥（可选）</label>
                <input
                  type="text"
                  value={settings.webhook_secret || ''}
                  onChange={e => setSettings({...settings, webhook_secret: e.target.value})}
                  placeholder="留空则不签名"
                  className="w-full ios-input px-4 py-3 rounded-xl text-sm font-mono"
                />
                <p className="text-xs text-gray-500">设置后将通过 X-Signature 头部发送 HMAC-SHA256 签名，用于验证请求合法性</p>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-bold text-gray-800">推送事件类型</label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { key: 'new_order', label: '新订单', icon: '🛒' },
                    { key: 'order_updated', label: '订单状态变更', icon: '📦' },
                    { key: 'message_received', label: '收到新消息', icon: '💬' },
                    { key: 'delivery_completed', label: '发货完成', icon: '✅' },
                    { key: 'account_status', label: '账号状态变更', icon: '⚠️' },
                    { key: 'system_log', label: '系统日志', icon: '📝' }
                  ].map(event => {
                    const enabled = (settings.webhook_events || '').split(',').filter((e: string) => e.trim()).includes(event.key);
                    return (
                      <button
                        key={event.key}
                        type="button"
                        onClick={() => toggleWebhookEvent(event.key)}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all border-2 ${
                          enabled
                            ? 'bg-green-50 border-green-500 text-green-700'
                            : 'bg-gray-50 border-gray-200 text-gray-600 hover:border-gray-300'
                        }`}
                      >
                        <span>{event.icon}</span>
                        <span>{event.label}</span>
                        {enabled && <CheckCircle className="w-4 h-4 ml-auto text-green-500" />}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-gray-500">勾选要推送的事件类型。不选则推送全部事件。</p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={handleTestWebhook}
                  disabled={testingWebhook || !settings.webhook_url}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-xl font-bold text-sm hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="w-4 h-4" />
                  {testingWebhook ? '发送中...' : '发送测试消息'}
                </button>
                {!settings.webhook_url && (
                  <span className="text-xs text-gray-400">请先填写 Webhook URL</span>
                )}
              </div>

              {testResult && (
                <div className={`p-4 rounded-xl text-sm ${
                  testResult.success
                    ? 'bg-green-50 text-green-700 border border-green-200'
                    : 'bg-red-50 text-red-700 border border-red-200'
                }`}>
                  <div className="font-bold mb-1">{testResult.success ? '✅ 连接成功' : '❌ 连接失败'}</div>
                  <div className="text-xs">{testResult.message}</div>
                </div>
              )}

              <div className="p-3 bg-blue-50 rounded-xl text-xs text-blue-700 space-y-1">
                <strong>💡 n8n 接入提示：</strong>
                <ul className="list-disc list-inside space-y-0.5 mt-1">
                  <li>在 n8n 中创建 Webhook 节点，选择 POST 方法</li>
                  <li>将 n8n 生成的 Webhook URL 填入上方输入框</li>
                  <li>配置触发条件后即可接收实时事件推送</li>
                  <li>请求体为 JSON 格式：包含 event_type、data、timestamp 字段</li>
                </ul>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Save Button */}
      <div className="fixed bottom-10 right-10 z-30">
        <button
            onClick={handleSave}
            disabled={saving}
            className="ios-btn-primary px-10 py-5 rounded-[2rem] text-lg shadow-2xl shadow-yellow-200 flex items-center gap-3 transform hover:scale-105 active:scale-95 transition-all disabled:opacity-70"
        >
            <Save className="w-6 h-6" />
            {saving ? '保存中...' : '保存所有配置'}
        </button>
      </div>

      {toasts.length > 0 && (
        <div className="fixed top-4 right-4 z-50 space-y-2">
          {toasts.map(toast => (
            <div
              key={toast.id}
              className={`px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 ${
                toast.type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
              }`}
            >
              {toast.type === 'success' && <CheckCircle className="w-5 h-5" />}
              <span className="font-medium">{toast.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Settings;
