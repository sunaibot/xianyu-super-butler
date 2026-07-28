import React, { useEffect, useState } from 'react';
import { Item, AccountDetail } from '../types';
import { getItems, getAccountDetails, syncItemsFromAccount, deleteItem, createItem, updateItem } from '../services/api';
import { Box, RefreshCw, ShoppingBag, Edit, Trash2, Plus, Save, X, Eye, EyeOff, CheckCircle } from 'lucide-react';

interface Toast {
  id: number;
  type: 'success' | 'error';
  message: string;
}

const ItemList: React.FC = () => {
  const [items, setItems] = useState<Item[]>([]);
  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState<Item | null>(null);
  const [editForm, setEditForm] = useState<Partial<Item>>({});
  const [addForm, setAddForm] = useState({
    cookie_id: '',
    item_id: '',
    item_title: '',
    item_price: '',
    item_image: '',
    is_multi_spec: false,
    is_multi_qty_ship: false
  });
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = (type: 'success' | 'error', message: string) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000);
  };

  const refreshItems = async () => {
    try {
      const data = await getItems();
      setItems(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('加载商品失败:', error);
    }
  };

  useEffect(() => {
    getAccountDetails().then(setAccounts);
    refreshItems();
  }, []);

  const handleSync = async () => {
      if (!selectedAccount) {
        showToast('error', '请先选择账号');
        return;
      }
      setLoading(true);
      try {
        await syncItemsFromAccount(selectedAccount);
        await refreshItems();
        showToast('success', '同步成功');
      } catch (error) {
        showToast('error', '同步失败');
      } finally {
        setLoading(false);
      }
  };

  const handleEdit = (item: Item) => {
    setSelectedItem(item);
    setEditForm({ ...item });
    setShowEditModal(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedItem) return;
    try {
      await updateItem(selectedItem.cookie_id, selectedItem.item_id, editForm);
      await refreshItems();
      setShowEditModal(false);
      showToast('success', '更新成功');
    } catch (error) {
      console.error('更新商品失败:', error);
      showToast('error', '更新失败，请重试');
    }
  };

  const handleDelete = async (item: Item) => {
    if (confirm(`确认删除商品"${item.item_title}"吗？`)) {
      try {
        await deleteItem(item.cookie_id, item.item_id);
        await refreshItems();
        showToast('success', '删除成功');
      } catch (error) {
        console.error('删除商品失败:', error);
        showToast('error', '删除失败，请重试');
      }
    }
  };

  const handleAddItem = async () => {
    if (!addForm.cookie_id) {
      showToast('error', '请选择账号');
      return;
    }
    try {
      await createItem(addForm.cookie_id, addForm);
      await refreshItems();
      setShowAddModal(false);
      setAddForm({
        cookie_id: '',
        item_id: '',
        item_title: '',
        item_price: '',
        item_image: '',
        is_multi_spec: false,
        is_multi_qty_ship: false
      });
      showToast('success', '添加成功');
    } catch (error) {
      console.error('添加商品失败:', error);
      showToast('error', '添加失败，请重试');
    }
  };

  const toggleMultiSpec = async (item: Item) => {
    try {
      await updateItem(item.cookie_id, item.item_id, { is_multi_spec: !item.is_multi_spec });
      await refreshItems();
    } catch (error) {
      console.error('切换状态失败:', error);
      showToast('error', '切换失败');
    }
  };

  const toggleMultiQty = async (item: Item) => {
    try {
      await updateItem(item.cookie_id, item.item_id, { is_multi_qty_ship: !item.is_multi_qty_ship });
      await refreshItems();
    } catch (error) {
      console.error('切换状态失败:', error);
      showToast('error', '切换失败');
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold text-gray-900">商品管理</h2>
          <p className="text-gray-500 mt-2 text-sm">监控并管理所有账号下的闲鱼商品。</p>
        </div>
        <div className="flex gap-3">
            <select
                className="ios-input px-4 py-3 rounded-xl text-sm"
                value={selectedAccount}
                onChange={e => setSelectedAccount(e.target.value)}
            >
                <option value="">选择账号以同步</option>
                {accounts.map(acc => (
                    <option key={acc.id} value={acc.id}>{acc.nickname}</option>
                ))}
            </select>
            <button
                onClick={handleSync}
                disabled={loading || !selectedAccount}
                className="ios-btn-primary flex items-center gap-2 px-6 py-3 rounded-2xl font-bold shadow-lg shadow-yellow-200 disabled:opacity-50"
            >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                同步商品
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-5 py-3 rounded-2xl font-bold bg-gray-900 text-white hover:bg-gray-800 transition-colors flex items-center gap-2 shadow-lg"
            >
              <Plus className="w-4 h-4" />
              添加商品
            </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {items.map(item => (
              <div key={`${item.cookie_id}-${item.item_id}`} className="ios-card p-4 rounded-3xl hover:shadow-lg transition-all group relative">
                  <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                      <button
                        onClick={() => handleEdit(item)}
                        className="p-2 bg-white/90 backdrop-blur rounded-lg shadow-md hover:bg-[#FFE815] transition-colors"
                        title="编辑"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(item)}
                        className="p-2 bg-white/90 backdrop-blur rounded-lg shadow-md hover:bg-red-100 text-red-500 transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                  </div>
                  <div className="aspect-square bg-gray-100 rounded-2xl mb-4 overflow-hidden relative">
                      {item.item_image ? (
                          <img src={item.item_image} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                      ) : (
                          <div className="w-full h-full flex items-center justify-center text-gray-300">
                              <Box className="w-10 h-10" />
                          </div>
                      )}
                      <div className="absolute top-2 left-2 bg-black/50 backdrop-blur-md text-white text-xs font-bold px-2 py-1 rounded-lg">
                          ¥{item.item_price}
                      </div>
                  </div>
                  <h3 className="font-bold text-gray-900 line-clamp-2 text-sm mb-2 h-10">{item.item_title}</h3>
                  <div className="flex justify-between items-center text-xs text-gray-500 mb-2">
                      <span className="bg-gray-100 px-2 py-1 rounded-md truncate max-w-[100px]">ID: {item.item_id}</span>
                  </div>
                  <div className="flex gap-2">
                      <button
                        onClick={() => toggleMultiSpec(item)}
                        className={`flex-1 text-xs font-bold px-2 py-1.5 rounded-lg transition-colors ${
                          item.is_multi_spec
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                        }`}
                      >
                        多规格
                      </button>
                      <button
                        onClick={() => toggleMultiQty(item)}
                        className={`flex-1 text-xs font-bold px-2 py-1.5 rounded-lg transition-colors ${
                          item.is_multi_qty_ship
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                        }`}
                      >
                        多数量发货
                      </button>
                  </div>
              </div>
          ))}
          {items.length === 0 && (
             <div className="col-span-full py-20 text-center text-gray-400">
                 <ShoppingBag className="w-12 h-12 mx-auto mb-4 opacity-30" />
                 暂无商品数据，请选择账号进行同步
             </div>
          )}
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

export default ItemList;
