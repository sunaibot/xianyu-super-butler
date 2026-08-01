import React, { useEffect, useState } from 'react';
import { Item, AccountDetail, ProductExtractionResult, ProductDedupResult } from '../types';
import { getItems, getAccountDetails, syncItemsFromAccount, deleteItem, updateItem, updateItemMultiSpec, updateItemMultiQty, extractProduct, publishProduct, dedupProducts } from '../services/api';
import { Box, RefreshCw, ShoppingBag, Edit, Trash2, Save, CheckCircle, Download, Upload, GitMerge, Link2 } from 'lucide-react';
import { useNavigate } from '../contexts/NavigateContext';
import { useToast } from './Toast';
import Modal from './ui/Modal';

const ItemList: React.FC = () => {
  const { navigate, consumeParams } = useNavigate();
  const { showToast } = useToast();
  const [items, setItems] = useState<Item[]>([]);
  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState<Item | null>(null);
  const [editForm, setEditForm] = useState<Partial<Item>>({});

  // 统一的发布商品流程（合并原"添加商品"+"抓取商品"+"发布商品"）
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [publishForm, setPublishForm] = useState({
    title: '',
    price: '',
    description: '',
    images: [] as string[],
    category: '',
    cookie_id: '',    // 发布到哪个账号
  });
  const [publishLoading, setPublishLoading] = useState(false);

  // URL 抓取（嵌入发布弹窗内部）
  const [extractUrl, setExtractUrl] = useState('');
  const [extractLoading, setExtractLoading] = useState(false);

  // Product dedup states
  const [showDedupModal, setShowDedupModal] = useState(false);
  const [dedupInput, setDedupInput] = useState('');
  const [dedupResult, setDedupResult] = useState<ProductDedupResult | null>(null);
  const [dedupLoading, setDedupLoading] = useState(false);

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

  // 消费跨页面联动参数（如从账号列表跳转过来，携带 cookie_id 过滤）
  useEffect(() => {
    const params = consumeParams();
    if (params?.filter?.cookie_id) {
      setSelectedAccount(String(params.filter.cookie_id));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const toggleMultiSpec = async (item: Item) => {
    try {
      await updateItemMultiSpec(item.cookie_id, item.item_id, !item.is_multi_spec);
      await refreshItems();
    } catch (error) {
      console.error('切换状态失败:', error);
      showToast('error', '切换失败');
    }
  };

  const toggleMultiQty = async (item: Item) => {
    try {
      await updateItemMultiQty(item.cookie_id, item.item_id, !item.is_multi_qty_ship);
      await refreshItems();
    } catch (error) {
      console.error('切换状态失败:', error);
      showToast('error', '切换失败');
    }
  };

  // 从 URL 抓取商品信息并填充到发布表单
  const handleExtractAndFill = async () => {
    if (!extractUrl.trim()) {
      showToast('error', '请输入商品URL');
      return;
    }
    setExtractLoading(true);
    try {
      const result = await extractProduct(extractUrl);
      if (result.success && result.product) {
        setPublishForm(prev => ({
          ...prev,
          title: result.product!.title || prev.title,
          price: result.product!.price || prev.price,
          description: result.product!.description || prev.description,
          images: result.product!.images || [],
          category: result.product!.category || prev.category,
        }));
        showToast('success', '已填充抓取的商品信息');
      } else {
        showToast('error', result.message || '抓取失败');
      }
    } catch (error) {
      console.error('抓取商品失败:', error);
      showToast('error', '抓取失败，请重试');
    } finally {
      setExtractLoading(false);
    }
  };

  const openPublishModal = () => {
    setShowPublishModal(true);
    setPublishForm({ title: '', price: '', description: '', images: [], category: '', cookie_id: selectedAccount });
    setExtractUrl('');
  };

  // 统一的发布流程：发布到闲鱼 + 添加到本地监控
  const handlePublishProduct = async () => {
    if (!publishForm.title || !publishForm.price) {
      showToast('error', '请填写商品标题和价格');
      return;
    }
    setPublishLoading(true);
    try {
      // 1. 发布到闲鱼
      const result = await publishProduct({
        title: publishForm.title,
        price: publishForm.price,
        description: publishForm.description,
        images: publishForm.images,
        category: publishForm.category,
      });
      if (result.success) {
        showToast('success', '商品发布成功');
        setShowPublishModal(false);
        // 2. 刷新商品列表（发布后同步可拉取最新商品）
        await refreshItems();
      } else {
        showToast('error', result.message || '发布失败');
      }
    } catch (error) {
      console.error('发布商品失败:', error);
      showToast('error', '发布失败，请重试');
    } finally {
      setPublishLoading(false);
    }
  };

  // Product dedup
  const handleDedupProducts = async () => {
    if (!dedupInput.trim()) {
      showToast('error', '请输入要去重的商品信息');
      return;
    }
    setDedupLoading(true);
    try {
      const lines = dedupInput.split('\n').filter(l => l.trim());
      const titles = lines.map(l => l.trim());
      const result = await dedupProducts({ item_titles: titles });
      setDedupResult(result);
      if (result.duplicates?.length > 0) {
        showToast('error', `发现 ${result.duplicates.length} 组重复商品`);
      } else {
        showToast('success', '未发现重复商品');
      }
    } catch (error) {
      console.error('商品去重失败:', error);
      showToast('error', '去重失败，请重试');
    } finally {
      setDedupLoading(false);
    }
  };

  const toggleImageInPublish = (imageUrl: string) => {
    setPublishForm(prev => ({
      ...prev,
      images: prev.images.includes(imageUrl)
        ? prev.images.filter(url => url !== imageUrl)
        : [...prev.images, imageUrl]
    }));
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold text-gray-900">商品管理</h2>
          <p className="text-gray-500 mt-2 text-sm">监控并管理所有账号下的闲鱼商品。</p>
        </div>
        <div className="flex gap-3 flex-wrap">
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
              onClick={openPublishModal}
              className="px-5 py-3 rounded-2xl font-bold bg-green-500 text-white hover:bg-green-600 transition-colors flex items-center gap-2 shadow-lg"
              title="发布新商品到闲鱼（支持从URL抓取填充）"
            >
              <Upload className="w-4 h-4" />
              发布商品
            </button>
            <button
              onClick={() => { setShowDedupModal(true); setDedupResult(null); setDedupInput(''); }}
              className="px-5 py-3 rounded-2xl font-bold bg-purple-500 text-white hover:bg-purple-600 transition-colors flex items-center gap-2 shadow-lg"
              title="检测重复商品"
            >
              <GitMerge className="w-4 h-4" />
              商品去重
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
                          <img src={item.item_image} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
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
                  <button
                    onClick={() => navigate('orders', { filter: { item_id: item.item_id } })}
                    className="w-full mt-2 text-xs font-bold px-2 py-1.5 min-h-[36px] rounded-lg bg-yellow-50 text-yellow-700 hover:bg-yellow-100 transition-colors flex items-center justify-center gap-1"
                    title="查看该商品的关联订单"
                  >
                    <ShoppingBag className="w-3 h-3" /> 查看订单
                  </button>
              </div>
          ))}
          {items.length === 0 && (
             <div className="col-span-full py-20 text-center text-gray-400">
                 <ShoppingBag className="w-12 h-12 mx-auto mb-4 opacity-30" />
                 暂无商品数据，请选择账号进行同步
             </div>
          )}
      </div>

      {/* 统一的发布商品 Modal（整合了原"抓取商品"+"添加商品"+"发布商品"） */}
      <Modal
        isOpen={showPublishModal}
        onClose={() => setShowPublishModal(false)}
        title={
          <span className="flex items-center gap-2">
            <Upload className="w-5 h-5 text-green-500" />
            发布商品
          </span>
        }
        size="md"
      >
        <div className="space-y-4">
          {/* 从 URL 抓取填充 */}
          <div className="p-4 bg-blue-50 rounded-xl space-y-2">
            <label className="block text-sm font-bold text-blue-800 flex items-center gap-1">
              <Link2 className="w-4 h-4" />
              从闲鱼URL抓取填充（可选）
            </label>
            <div className="flex gap-2">
              <input
                type="url"
                aria-label="商品URL"
                inputMode="url"
                value={extractUrl}
                onChange={e => setExtractUrl(e.target.value)}
                placeholder="https://www.goofish.com/item?id=..."
                className="flex-1 ios-input px-4 py-2.5 rounded-xl text-sm"
              />
              <button
                onClick={handleExtractAndFill}
                disabled={extractLoading || !extractUrl.trim()}
                className="px-4 py-2.5 bg-blue-500 text-white rounded-xl font-bold text-sm hover:bg-blue-600 transition-colors disabled:opacity-50 flex items-center gap-1 whitespace-nowrap"
              >
                <Download className="w-4 h-4" />
                {extractLoading ? '抓取中...' : '抓取'}
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-800">商品标题 *</label>
            <input
              type="text"
              aria-label="商品标题"
              value={publishForm.title}
              onChange={e => setPublishForm({...publishForm, title: e.target.value})}
              className="w-full ios-input px-4 py-3 rounded-xl text-sm"
              placeholder="请输入商品标题"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="block text-sm font-bold text-gray-800">价格 *</label>
              <input
                type="text"
                aria-label="价格"
                inputMode="numeric"
                value={publishForm.price}
                onChange={e => setPublishForm({...publishForm, price: e.target.value})}
                className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                placeholder="¥0.00"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-bold text-gray-800">分类</label>
              <input
                type="text"
                aria-label="分类"
                value={publishForm.category}
                onChange={e => setPublishForm({...publishForm, category: e.target.value})}
                className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                placeholder="商品分类"
              />
            </div>
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-800">商品描述</label>
            <textarea
              value={publishForm.description}
              onChange={e => setPublishForm({...publishForm, description: e.target.value})}
              className="w-full ios-input px-4 py-3 rounded-xl text-sm min-h-[100px] resize-none"
              placeholder="请输入商品描述"
            />
          </div>
          {publishForm.images.length > 0 && (
            <div className="space-y-2">
              <label className="block text-sm font-bold text-gray-800">选择图片 (点击取消选择)</label>
              <div className="grid grid-cols-3 gap-2">
                {publishForm.images.map((img, idx) => (
                  <div
                    key={idx}
                    onClick={() => toggleImageInPublish(img)}
                    className={`relative cursor-pointer rounded-lg border-2 ${publishForm.images.includes(img) ? 'border-green-500' : 'border-transparent'}`}
                  >
                    <img src={img} alt="" className="w-full aspect-square object-cover rounded-lg" />
                    {publishForm.images.includes(img) && (
                      <div className="absolute inset-0 bg-green-500/30 rounded-lg flex items-center justify-center">
                        <CheckCircle className="w-6 h-6 text-white" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={handlePublishProduct}
            disabled={publishLoading || !publishForm.title || !publishForm.price}
            className="w-full py-3 bg-green-500 text-white rounded-xl font-bold hover:bg-green-600 transition-colors disabled:opacity-50"
          >
            {publishLoading ? '发布中...' : '发布商品'}
          </button>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={showEditModal && !!selectedItem}
        onClose={() => setShowEditModal(false)}
        title={
          <span className="flex items-center gap-2">
            <Edit className="w-5 h-5 text-yellow-500" />
            编辑商品
          </span>
        }
        size="md"
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-800">商品标题</label>
            <input
              type="text"
              aria-label="商品标题"
              value={editForm.item_title || ''}
              onChange={e => setEditForm({...editForm, item_title: e.target.value})}
              className="w-full ios-input px-4 py-3 rounded-xl text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="block text-sm font-bold text-gray-800">价格</label>
              <input
                type="text"
                aria-label="价格"
                inputMode="numeric"
                value={editForm.item_price || ''}
                onChange={e => setEditForm({...editForm, item_price: e.target.value})}
                className="w-full ios-input px-4 py-3 rounded-xl text-sm"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-bold text-gray-800">图片URL</label>
              <input
                type="text"
                aria-label="图片URL"
                inputMode="url"
                value={editForm.item_image || ''}
                onChange={e => setEditForm({...editForm, item_image: e.target.value})}
                className="w-full ios-input px-4 py-3 rounded-xl text-sm"
                placeholder="图片URL"
              />
            </div>
          </div>
          <button
            onClick={handleSaveEdit}
            className="w-full py-3 bg-yellow-400 text-gray-900 rounded-xl font-bold hover:bg-yellow-500 transition-colors flex items-center justify-center gap-2"
          >
            <Save className="w-4 h-4" />
            保存
          </button>
        </div>
      </Modal>

      {/* Dedup Products Modal */}
      <Modal
        isOpen={showDedupModal}
        onClose={() => { setShowDedupModal(false); setDedupResult(null); }}
        title={
          <span className="flex items-center gap-2">
            <GitMerge className="w-5 h-5 text-purple-500" />
            商品去重检测
          </span>
        }
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500">每行输入一个商品标题，系统将检测重复商品</p>
          <div className="space-y-2">
            <textarea
              value={dedupInput}
              onChange={e => setDedupInput(e.target.value)}
              className="w-full ios-input px-4 py-3 rounded-xl text-sm min-h-[150px] resize-none"
              placeholder={'示例商品标题\n示例商品标题\n另一个商品标题...'}
            />
          </div>
          <button
            onClick={handleDedupProducts}
            disabled={dedupLoading || !dedupInput.trim()}
            className="w-full py-3 bg-purple-500 text-white rounded-xl font-bold hover:bg-purple-600 transition-colors disabled:opacity-50"
          >
            {dedupLoading ? '检测中...' : '开始检测'}
          </button>
          {dedupResult && (
            <div className="mt-4 space-y-3">
              {dedupResult.duplicates?.length > 0 ? (
                <div className="p-4 bg-red-50 rounded-xl border border-red-200">
                  <div className="font-bold text-red-700 mb-2">⚠️ 发现 {dedupResult.duplicates.length} 组重复商品</div>
                  <div className="space-y-2">
                    {dedupResult.duplicates.map((dup, idx) => (
                      <div key={idx} className="text-sm bg-white p-2 rounded-lg">
                        <div className="text-gray-700">
                          <strong>#{dup.index1 + 1}</strong> ↔ <strong>#{dup.index2 + 1}</strong>
                          <span className="text-xs text-gray-500 ml-2">相似度: {(dup.similarity * 100).toFixed(1)}%</span>
                        </div>
                        <div className="text-xs text-gray-500">原因: {dup.reason}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-green-50 rounded-xl border border-green-200 text-green-700">
                  ✅ 未发现重复商品
                </div>
              )}
            </div>
          )}
          <div className="p-3 bg-blue-50 rounded-xl text-xs text-blue-700">
            <strong>💡 去重说明:</strong>
            <ul className="list-disc list-inside space-y-0.5 mt-1">
              <li>基于文本相似度检测重复商品</li>
              <li>支持标题关键词匹配</li>
              <li>检测结果仅供参考</li>
            </ul>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ItemList;
