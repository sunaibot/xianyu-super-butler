import React, { useEffect, useState } from 'react';
import { ShippingRule } from '../types';
import { getShippingRules, updateShippingRule, deleteShippingRule } from '../services/api';
import { useToast } from './Toast';
import { useConfirm } from '../hooks/useConfirm';
import Modal from './ui/Modal';
import { Plus, Trash2, Edit, Save, AlertCircle, RefreshCw } from 'lucide-react';

const Rules: React.FC = () => {
  const { showToast } = useToast();
  const confirm = useConfirm();
  const [shippingRules, setShippingRules] = useState<ShippingRule[]>([]);
  const [loading, setLoading] = useState(false);

  // 弹窗状态
  const [showShippingModal, setShowShippingModal] = useState(false);
  const [editingShippingRule, setEditingShippingRule] = useState<Partial<ShippingRule> | null>(null);

  // Load data
  const refresh = async () => {
      setLoading(true);
      try {
          const data = await getShippingRules();
          setShippingRules(data);
      } finally {
          setLoading(false);
      }
  };

  useEffect(() => {
      refresh();
  }, []);

  // Handlers
  const handleToggleShipping = async (rule: ShippingRule) => {
      await updateShippingRule({ ...rule, enabled: !rule.enabled });
      refresh();
      showToast('success', rule.enabled ? '规则已禁用' : '规则已启用');
  };
  const handleDeleteShipping = async (id: string) => {
      if(await confirm({ title: '确认删除发货规则', content: '确定删除该发货规则吗？此操作不可恢复。', variant: 'danger' })) {
          await deleteShippingRule(id);
          refresh();
          showToast('success', '规则已删除');
      }
  };

  // 发货规则增删改
  const handleAddShippingRule = () => {
    setEditingShippingRule({
      name: '',
      item_keyword: '',
      card_group_id: 0,
      card_group_name: '',
      priority: 1,
      enabled: true
    });
    setShowShippingModal(true);
  };

  const handleEditShippingRule = (rule: ShippingRule) => {
    setEditingShippingRule({ ...rule });
    setShowShippingModal(true);
  };

  const handleSaveShippingRule = async () => {
    if (!editingShippingRule) return;
    try {
      await updateShippingRule(editingShippingRule);
      setShowShippingModal(false);
      refresh();
      showToast('success', '保存成功');
    } catch (error) {
      console.error('保存发货规则失败:', error);
      showToast('error', '保存失败，请重试');
    }
  };

  return (
    <div className="space-y-6 animate-fade-in pb-20">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-extrabold text-gray-900">智能策略</h2>
          <p className="text-gray-500 mt-2 font-medium">配置商品关键词与卡密组的自动发货规则。</p>
        </div>
        <button onClick={refresh} className="p-3 bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow">
            <RefreshCw className={`w-5 h-5 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Content Area */}
      <div className="ios-card bg-white rounded-[2rem] p-6 min-h-[500px]">
          <div className="space-y-4">
              <div className="flex justify-between items-center mb-6">
                  <div className="flex items-center gap-2 text-sm text-yellow-700 bg-yellow-50 px-4 py-2 rounded-xl">
                      <AlertCircle className="w-4 h-4" />
                      当订单商品标题包含关键词时，自动发送对应卡密。
                  </div>
                  <button onClick={handleAddShippingRule} className="ios-btn-primary px-5 py-3 rounded-2xl text-sm font-bold flex items-center gap-2 shadow-lg shadow-yellow-200">
                      <Plus className="w-4 h-4" /> 新增发货规则
                  </button>
              </div>
              
              <div className="space-y-3">
                  {shippingRules.map(rule => (
                      <div key={rule.id} className="flex items-center justify-between p-5 rounded-2xl border border-gray-100 bg-[#F7F8FA] hover:bg-white hover:shadow-lg transition-all duration-300">
                          <div className="flex items-center gap-4">
                              <div className={`w-12 h-12 rounded-2xl flex items-center justify-center font-bold text-lg ${rule.enabled ? 'bg-black text-[#FFE815]' : 'bg-gray-200 text-gray-400'}`}>
                                  {rule.priority}
                              </div>
                              <div>
                                  <h3 className="font-bold text-gray-900 text-lg">{rule.name}</h3>
                                  <div className="flex items-center gap-3 mt-1 text-sm text-gray-500 font-medium">
                                      <span className="bg-blue-50 text-blue-600 px-2 py-0.5 rounded-lg">关键词: {rule.item_keyword}</span>
                                      <span>→</span>
                                      <span className="bg-purple-50 text-purple-600 px-2 py-0.5 rounded-lg">卡密组: {rule.card_group_name || `ID:${rule.card_group_id}`}</span>
                                  </div>
                              </div>
                          </div>
                          <div className="flex items-center gap-3">
                              <button
                                onClick={() => handleEditShippingRule(rule)}
                                className="p-2 text-gray-400 hover:text-black hover:bg-gray-100 rounded-xl transition-colors"
                                title="编辑"
                              >
                                <Edit className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleToggleShipping(rule)}
                                className={`w-12 h-8 rounded-full relative transition-colors ${rule.enabled ? 'bg-green-500' : 'bg-gray-300'}`}
                              >
                                  <div className={`absolute top-1 w-6 h-6 bg-white rounded-full shadow-sm transition-transform ${rule.enabled ? 'left-5' : 'left-1'}`}></div>
                              </button>
                              <button onClick={() => handleDeleteShipping(rule.id)} className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-colors">
                                  <Trash2 className="w-5 h-5" />
                              </button>
                          </div>
                      </div>
                  ))}
                  {shippingRules.length === 0 && <div className="text-center py-20 text-gray-400">暂无规则，点击"新增发货规则"添加第一条规则</div>}
              </div>
          </div>
      </div>

      {/* Shipping Rule Modal */}
      <Modal
        isOpen={showShippingModal}
        onClose={() => setShowShippingModal(false)}
        title={editingShippingRule?.id ? '编辑发货规则' : '新增发货规则'}
        size="md"
        footer={
          <div className="flex gap-3">
            <button
              onClick={() => setShowShippingModal(false)}
              className="flex-1 px-6 py-3 rounded-xl font-bold bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSaveShippingRule}
              className="flex-1 ios-btn-primary px-6 py-3 rounded-xl font-bold flex items-center justify-center gap-2"
            >
              <Save className="w-4 h-4" />
              保存规则
            </button>
          </div>
        }
      >
        <div className="space-y-5">
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">规则名称</label>
            <input
              type="text"
              aria-label="规则名称"
              value={editingShippingRule?.name || ''}
              onChange={(e) => setEditingShippingRule({ ...editingShippingRule, name: e.target.value })}
              placeholder="例如：VIP会员发货"
              className="w-full ios-input px-4 py-3 rounded-xl"
            />
          </div>

          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">商品关键词</label>
            <input
              type="text"
              aria-label="商品关键词"
              value={editingShippingRule?.item_keyword || ''}
              onChange={(e) => setEditingShippingRule({ ...editingShippingRule, item_keyword: e.target.value })}
              placeholder="商品标题中包含的关键词"
              className="w-full ios-input px-4 py-3 rounded-xl"
            />
          </div>

          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">卡密组ID</label>
            <input
              type="number"
              aria-label="卡密组ID"
              inputMode="numeric"
              value={editingShippingRule?.card_group_id || 0}
              onChange={(e) => setEditingShippingRule({ ...editingShippingRule, card_group_id: parseInt(e.target.value) || 0 })}
              placeholder="输入卡密组ID"
              className="w-full ios-input px-4 py-3 rounded-xl"
            />
          </div>

          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">优先级</label>
            <input
              type="number"
              aria-label="优先级"
              inputMode="numeric"
              value={editingShippingRule?.priority || 1}
              onChange={(e) => setEditingShippingRule({ ...editingShippingRule, priority: parseInt(e.target.value) || 1 })}
              min="1"
              className="w-full ios-input px-4 py-3 rounded-xl"
            />
            <p className="text-xs text-gray-500 mt-1">数字越小优先级越高</p>
          </div>

          <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
            <span className="font-bold text-gray-900">启用状态</span>
            <button
              type="button"
              onClick={() => setEditingShippingRule({ ...editingShippingRule, enabled: !editingShippingRule?.enabled })}
              className={`w-14 h-8 rounded-full transition-colors duration-300 relative ${
                editingShippingRule?.enabled ? 'bg-[#FFE815]' : 'bg-gray-300'
              }`}
            >
              <span
                className={`absolute top-1 w-6 h-6 bg-white rounded-full shadow-md transition-transform duration-300 block ${
                  editingShippingRule?.enabled ? 'translate-x-7' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Rules;
