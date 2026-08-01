import React, { useEffect, useState } from 'react';
import { Order, OrderStatus, Item } from '../types';
import { getOrders, syncOrders, syncSingleOrder, manualShipOrder, updateOrder, deleteOrder, importOrders, getItems } from '../services/api';
import { useToast } from './Toast';
import { useConfirm } from '../hooks/useConfirm';
import { useDebounce } from '../hooks/useDebounce';
import { usePagination } from '../hooks/usePagination';
import { OrderStatusBadge } from './ui/Badge';
import Modal from './ui/Modal';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import { useNavigate } from '../contexts/NavigateContext';
import { Search, MoreHorizontal, Truck, RefreshCw, Copy, ChevronLeft, ChevronRight, PackageCheck, Edit, Eye, Plus, Save, User as UserIcon, Phone, MapPin, Upload, ExternalLink, Trash2 } from 'lucide-react';

const OrderList: React.FC = () => {
  const { showToast } = useToast();
  const { onEvent } = useWebSocketContext();
  const { consumeParams } = useNavigate();
  const confirm = useConfirm();
  const loadOrdersRef = React.useRef<() => void>(() => {});
  const [orders, setOrders] = useState<Order[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [itemNames, setItemNames] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState('all');
  const [searchText, setSearchText] = useState('');
  // 使用统一的 useDebounce hook（替代手写 setTimeout）
  const debouncedSearch = useDebounce(searchText, 300);
  // 使用统一的 usePagination hook（替代手写 page/totalPages 状态）
  const { page, totalPages, setPage, setTotalPages } = usePagination(1, 1);
  const [loading, setLoading] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [editingOrder, setEditingOrder] = useState<Partial<Order> | null>(null);
  const [editForm, setEditForm] = useState<Partial<Order>>({});
  const [importText, setImportText] = useState('');
  const [showShipModal, setShowShipModal] = useState(false);
  const [shipOrderId, setShipOrderId] = useState<string>('');
  const [shipLoading, setShipLoading] = useState(false);
  const [shipResult, setShipResult] = useState<{success: boolean; message: string} | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importFormData, setImportFormData] = useState({
    order_id: '',
    item_id: '',
    buyer_id: '',
    receiver_name: '',
    receiver_phone: '',
    receiver_address: '',
    status: 'pending_ship' as OrderStatus,
    quantity: 1,
    amount: ''
  });
  const [syncingOrderId, setSyncingOrderId] = useState<string | null>(null);
  const [deletingOrderId, setDeletingOrderId] = useState<string | null>(null);

  // 消费跨页面联动参数（如从商品列表跳转过来，携带 item_id 过滤）
  useEffect(() => {
    const params = consumeParams();
    if (params?.filter?.item_id) {
      setSearchText(String(params.filter.item_id));
      setFilter('all');
      setPage(1);
    } else if (params?.filter?.cookie_id) {
      setSearchText(String(params.filter.cookie_id));
      setPage(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadOrders = async () => {
      setLoading(true);
      try {
          const res = await getOrders(undefined, filter, page, 20, debouncedSearch || undefined);
          setOrders(res.data);
          setTotalPages(res.total_pages || 1);
      } catch (e) {
          console.error('加载订单失败:', e);
      } finally {
          setLoading(false);
      }
  };

  loadOrdersRef.current = loadOrders;

  const getItemNameById = (orderId: string, orderItemTitle?: string): string => {
      if (orderItemTitle && orderItemTitle.trim()) {
          return orderItemTitle;
      }
      if (itemNames[orderId]) {
          return itemNames[orderId];
      }
      const matchingItem = items.find(item => {
          if (orderItemTitle && item.item_title) {
              const orderTitleLower = orderItemTitle.toLowerCase();
              const itemTitleLower = item.item_title.toLowerCase();
              return itemTitleLower.includes(orderTitleLower) || orderTitleLower.includes(itemTitleLower);
          }
          return false;
      });
      if (matchingItem?.item_title) {
          return matchingItem.item_title;
      }
      return '未知商品';
  };

  const buildItemNamesMap = () => {
      const namesMap: Record<string, string> = {};
      items.forEach(item => {
          if (item.item_id) {
              namesMap[item.item_id] = item.item_title || item.item_id;
          }
      });
      setItemNames(namesMap);
  };

  useEffect(() => {
    loadOrders();
    getItems().then((itemsList) => {
      setItems(itemsList);
      buildItemNamesMap();
    }).catch((e) => {
      console.error('加载商品列表失败:', e);
    });
  }, [filter, page, debouncedSearch]);

  useEffect(() => {
    const offNewOrder = onEvent('new_order', () => {
      showToast('success', '收到新订单，正在刷新列表...');
      if (page === 1) {
        loadOrdersRef.current();
      } else {
        setPage(1);
      }
    });
    const offOrderUpdated = onEvent('order_updated', () => {
      loadOrdersRef.current();
    });
    const offDelivery = onEvent('delivery_completed', () => {
      showToast('success', '发货完成，正在更新订单状态...');
      loadOrdersRef.current();
    });
    return () => {
      offNewOrder();
      offOrderUpdated();
      offDelivery();
    };
  }, [onEvent, page, showToast]);

  const handleSync = async () => {
      setLoading(true);
      await syncOrders();
      loadOrders();
  };

  const handleShip = (id: string) => {
      setShipOrderId(id);
      setShipResult(null);
      setShowShipModal(true);
  };

  const executeShip = async (mode: 'status_only' | 'full_delivery') => {
      setShipLoading(true);
      setShipResult(null);
      try {
          const res = await manualShipOrder([shipOrderId], mode);
          const result = res?.results?.[0];
          if (result?.success) {
              setShipResult({ success: true, message: result.message });
              loadOrders();
          } else {
              setShipResult({ success: false, message: result?.message || '发货失败' });
          }
      } catch (e: any) {
          setShipResult({ success: false, message: e?.message || '请求失败' });
      } finally {
          setShipLoading(false);
      }
  };

  const handleViewDetail = (order: Order) => {
    setSelectedOrder(order);
    setShowDetailModal(true);
  };

  const handleEdit = (order: Order) => {
    setEditingOrder({ ...order });
    setShowEditModal(true);
  };

  const handleSaveEdit = async () => {
    if (!editingOrder || !editingOrder.order_id) return;
    try {
      // 映射前端字段到后端期望的字段名
      const updateData: Record<string, any> = {};

      if (editingOrder.status !== undefined) {
        updateData.order_status = editingOrder.status;
      }
      if (editingOrder.buyer_id !== undefined) {
        updateData.buyer_id = editingOrder.buyer_id;
      }
      if (editingOrder.amount !== undefined) {
        updateData.amount = editingOrder.amount;
      }
      if (editingOrder.receiver_name !== undefined) {
        updateData.receiver_name = editingOrder.receiver_name;
      }
      if (editingOrder.receiver_phone !== undefined) {
        updateData.receiver_phone = editingOrder.receiver_phone;
      }
      if (editingOrder.receiver_address !== undefined) {
        updateData.receiver_address = editingOrder.receiver_address;
      }
      if (editingOrder.item_id !== undefined) {
        updateData.item_id = editingOrder.item_id;
      }
      if (editingOrder.quantity !== undefined) {
        updateData.quantity = editingOrder.quantity;
      }

      await updateOrder(editingOrder.order_id, updateData);
      setShowEditModal(false);
      setEditingOrder(null);
      loadOrders();
    } catch (error) {
      console.error('更新订单失败:', error);
      showToast('error', '更新失败，请重试');
    }
  };

  const handleImportOrders = async () => {
    try {
      const orders = JSON.parse(importText);
      const result = await importOrders(Array.isArray(orders) ? orders : [orders]);

      // 关闭弹窗并刷新列表
      setShowImportModal(false);
      setImportText('');
      loadOrders();

      // 展示详细导入结果（成功/失败计数），而非笼统的"成功"
      if (result && typeof result === 'object') {
        const ok = result.success_count ?? 0;
        const fail = result.failed_count ?? 0;
        if (fail > 0) {
          showToast('info', `导入完成: 成功 ${ok} 个, 失败 ${fail} 个`);
        } else {
          showToast('success', `导入完成: 共 ${ok} 个订单`);
        }
      } else {
        showToast('success', '订单导入成功');
      }
    } catch (error) {
      showToast('error', '导入失败，请检查JSON格式');
    }
  };

  const handleSyncSingle = async (orderId: string) => {
    setSyncingOrderId(orderId);
    try {
      const result = await syncSingleOrder(orderId);
      if (result.success) {
        await loadOrders();
      } else {
        showToast('error', result.message || '同步失败');
      }
    } catch (error: any) {
      console.error('同步订单失败:', error);
      showToast('error', error?.message || '同步失败，请重试');
    } finally {
      setSyncingOrderId(null);
    }
  };

  const handleDelete = async (orderId: string) => {
    if (!(await confirm({ title: '确认删除订单', content: '确认删除该订单吗？删除后无法恢复。', variant: 'danger' }))) return;
    setDeletingOrderId(orderId);
    try {
      await deleteOrder(orderId);
      loadOrders();
    } catch (error: any) {
      console.error('删除订单失败:', error);
      showToast('error', error?.message || '删除失败，请重试');
    } finally {
      setDeletingOrderId(null);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4">
        <div>
          <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">订单中心</h2>
          <p className="text-gray-500 mt-2 font-medium">查看所有闲鱼交易记录与状态。</p>
        </div>
        <div className="flex items-center gap-3">
            <button onClick={loadOrders} className="p-3 rounded-2xl bg-white border border-gray-100 text-gray-600 hover:bg-gray-50 hover:text-black transition-colors shadow-sm">
                <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setShowImportModal(true)}
              className="px-5 py-3 rounded-2xl font-bold bg-gray-900 text-white hover:bg-gray-800 transition-colors text-sm flex items-center gap-2 shadow-lg"
            >
              <Plus className="w-4 h-4" />
              插入订单
            </button>
            <button onClick={handleSync} className="ios-btn-primary px-6 py-3 rounded-2xl font-bold shadow-lg shadow-yellow-200 text-sm flex items-center gap-2">
                <Truck className="w-5 h-5" />
                一键同步订单
            </button>
        </div>
      </div>

      <div className="ios-card rounded-[2rem] overflow-hidden shadow-lg border-0 bg-white">
        {/* Toolbar */}
        <div className="p-4 border-b border-gray-50 flex flex-col md:flex-row gap-4 justify-between items-center bg-[#FAFAFA]">
          <div className="flex gap-1 p-1 bg-gray-200/50 rounded-xl overflow-x-auto max-w-full">
             {[
                 {k:'all', v:'全部'},
                 {k:'shipped', v:'已发货'},
                 {k:'pending_ship', v:'待发货'},
                 {k:'cancelled', v:'已取消'},
                 {k:'refunding', v:'其他'}
             ].map(opt => (
                 <button
                    key={opt.k}
                    onClick={() => { setFilter(opt.k); setPage(1); setSearchText(''); }}
                    className={`px-5 py-2 rounded-lg text-sm font-bold transition-all whitespace-nowrap ${filter === opt.k ? 'bg-white text-black shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
                 >
                    {opt.v}
                 </button>
             ))}
          </div>
          <div className="relative w-full md:w-auto group">
             <Search className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-[#FFE815] transition-colors" />
             <input
                 type="text"
                 aria-label="搜索订单号/商品/买家"
                 inputMode="search"
                 placeholder="搜索订单号/商品/买家..."
                 value={searchText}
                 onChange={(e) => { setSearchText(e.target.value); setPage(1); }}
                 className="ios-input pl-10 pr-4 py-2.5 rounded-xl w-64 bg-white border-none shadow-sm focus:ring-0"
             />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto min-h-[400px]">
          <table className="w-full text-left border-collapse table-fixed">
            <thead>
              <tr className="bg-white text-gray-400 text-xs font-bold uppercase tracking-wider border-b border-gray-50">
                <th className="px-6 py-5" style={{width: '28%'}}>订单信息</th>
                <th className="px-6 py-5" style={{width: '26%'}}>买家信息</th>
                <th className="px-6 py-5" style={{width: '11%'}}>实付金额</th>
                <th className="px-6 py-5" style={{width: '13%'}}>当前状态</th>
                <th className="px-6 py-5 text-right" style={{width: '22%'}}>操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {orders.map((order) => (
                <tr key={order.id} className="hover:bg-[#FFFDE7]/50 transition-colors group">
                  <td className="px-6 py-5">
                    <div className="flex items-center gap-5">
                      <div className="w-14 h-14 rounded-xl bg-gray-100 overflow-hidden shadow-sm border border-gray-100 flex-shrink-0">
                        {order.item_image ? (
                            <img src={order.item_image} alt="" className="w-full h-full object-cover" />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-gray-300"><PackageCheck /></div>
                        )}
                      </div>
                      <div className="min-w-0">
                        <div className="font-bold text-gray-900 line-clamp-1 text-sm">
                          {getItemNameById(order.item_id, order.item_title)}
                        </div>
                        <div className="text-xs text-gray-500 mt-1 font-medium">订单ID: {order.order_id}</div>
                        <div className="text-xs text-gray-400 mt-0.5">数量: {order.quantity} • {order.created_at}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-5">
                      <div className="flex flex-col gap-1">
                          <div className="text-xs text-gray-500">买家ID</div>
                          <div className="text-sm font-bold text-gray-800">{order.buyer_id}</div>
                          {order.receiver_name && (
                              <>
                                  <div className="text-xs text-gray-500">收货人</div>
                                  <div className="text-xs text-gray-600">{order.receiver_name}</div>
                              </>
                          )}
                          {order.receiver_phone && (
                              <>
                                  <div className="text-xs text-gray-500">联系电话</div>
                                  <div className="text-xs text-gray-600 font-mono">{order.receiver_phone}</div>
                              </>
                          )}
                          {order.receiver_address && (
                              <>
                                  <div className="text-xs text-gray-500">收货地址</div>
                                  <div className="text-xs text-gray-600 line-clamp-1">{order.receiver_address}</div>
                              </>
                          )}
                      </div>
                  </td>
                  <td className="px-6 py-5 text-base font-extrabold text-gray-900 font-feature-settings-tnum">¥{order.amount}</td>
                  <td className="px-6 py-5">
                    <OrderStatusBadge status={order.status} />
                  </td>
                  <td className="px-6 py-5 text-right">
                    {order.status === 'pending_ship' && (
                        <button
                            onClick={() => handleShip(order.order_id)}
                            className="mr-2 text-white bg-black hover:bg-gray-800 shadow-lg shadow-gray-200 text-xs font-bold px-3 py-2 rounded-xl transition-all active:scale-95"
                        >
                            立即发货
                        </button>
                    )}
                    <a
                      href={`https://www.goofish.com/order-detail?orderId=${order.order_id}&role=seller`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mr-2 inline-flex text-gray-400 hover:text-amber-600 p-2 rounded-xl hover:bg-amber-50 transition-colors"
                      title="查看闲鱼详情"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
                    <button
                      onClick={() => handleViewDetail(order)}
                      className="mr-2 text-gray-400 hover:text-blue-600 p-2 rounded-xl hover:bg-blue-50 transition-colors"
                      title="查看详情"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleEdit(order)}
                      className="mr-2 text-gray-400 hover:text-black p-2 rounded-xl hover:bg-gray-100 transition-colors"
                      title="编辑订单"
                    >
                      <Edit className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleSyncSingle(order.order_id)}
                      disabled={syncingOrderId === order.order_id}
                      className="mr-2 text-gray-400 hover:text-green-600 p-2 rounded-xl hover:bg-green-50 transition-colors disabled:opacity-50"
                      title="同步订单"
                    >
                      <RefreshCw className={`w-4 h-4 ${syncingOrderId === order.order_id ? 'animate-spin' : ''}`} />
                    </button>
                    <button
                      onClick={() => handleDelete(order.order_id)}
                      disabled={deletingOrderId === order.order_id}
                      className="text-gray-400 hover:text-red-500 p-2 rounded-xl hover:bg-red-50 transition-colors disabled:opacity-50"
                      title="删除订单"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="p-4 border-t border-gray-50 flex items-center justify-between bg-white">
            <div className="text-sm text-gray-500 font-medium pl-2">
                第 {page} 页 / 共 {totalPages} 页
            </div>
            <div className="flex gap-2">
                <button
                    disabled={page <= 1}
                    onClick={() => setPage(p => p - 1)}
                    className="p-2.5 rounded-xl bg-gray-50 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed text-gray-600 transition-colors"
                >
                    <ChevronLeft className="w-5 h-5" />
                </button>
                <button
                    disabled={page >= totalPages}
                    onClick={() => setPage(p => p + 1)}
                    className="p-2.5 rounded-xl bg-gray-50 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed text-gray-600 transition-colors"
                >
                    <ChevronRight className="w-5 h-5" />
                </button>
            </div>
        </div>
      </div>

      {/* 订单详情弹窗 - 使用 Modal */}
      {showDetailModal && selectedOrder && (
        <Modal
          isOpen={showDetailModal}
          onClose={() => setShowDetailModal(false)}
          title="订单详情"
          size="lg"
          footer={
            <div className="flex gap-3 w-full">
              <button
                onClick={() => setShowDetailModal(false)}
                className="flex-1 px-6 py-3 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-800 font-bold transition-colors"
              >
                关闭
              </button>
              {selectedOrder.status === 'pending_ship' && (
                <button
                  onClick={() => {
                    setShowDetailModal(false);
                    handleShip(selectedOrder.order_id);
                  }}
                  className="flex-1 px-6 py-3 rounded-xl ios-btn-primary font-bold shadow-lg shadow-yellow-200"
                >
                  立即发货
                </button>
              )}
            </div>
          }
        >
          <div className="space-y-6">
            {/* Order Info */}
            <div className="space-y-4">
              <h4 className="text-lg font-bold text-gray-800">订单信息</h4>
              <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-xl">
                <div>
                  <div className="text-xs text-gray-500 mb-1">订单号</div>
                  <div className="font-mono text-sm font-bold text-gray-900">{selectedOrder.order_id}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">状态</div>
                  <OrderStatusBadge status={selectedOrder.status} />
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">实付金额</div>
                  <div className="text-lg font-extrabold text-gray-900">¥{selectedOrder.amount}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">数量</div>
                  <div className="font-bold text-gray-900">{selectedOrder.quantity}</div>
                </div>
                <div className="col-span-2">
                  <div className="text-xs text-gray-500 mb-1">创建时间</div>
                  <div className="text-sm font-medium text-gray-700">{selectedOrder.created_at}</div>
                </div>
              </div>
            </div>

            {/* Item Info */}
            <div className="space-y-4">
              <h4 className="text-lg font-bold text-gray-800">商品信息</h4>
              <div className="p-4 bg-gray-50 rounded-xl flex items-center gap-4">
                {selectedOrder.item_image && (
                  <img src={selectedOrder.item_image} alt="" className="w-20 h-20 rounded-xl object-cover border border-gray-200" />
                )}
                <div className="flex-1">
                  <div className="font-bold text-gray-900 mb-1">
                    {getItemNameById(selectedOrder.item_id, selectedOrder.item_title)}
                  </div>
                  <div className="text-sm text-gray-500">商品ID: {selectedOrder.item_id}</div>
                  {selectedOrder.item_price && (
                    <div className="text-sm text-gray-500 mt-1">标价: ¥{selectedOrder.item_price}</div>
                  )}
                </div>
              </div>
            </div>

            {/* Buyer Info */}
            <div className="space-y-4">
              <h4 className="text-lg font-bold text-gray-800">买家信息</h4>
              <div className="p-4 bg-gray-50 rounded-xl space-y-3">
                <div>
                  <div className="text-xs text-gray-500 mb-1">买家ID</div>
                  <div className="font-bold text-gray-900">{selectedOrder.buyer_id}</div>
                </div>
                {selectedOrder.receiver_name && (
                  <div>
                    <div className="text-xs text-gray-500 mb-1">收货人</div>
                    <div className="font-medium text-gray-700">{selectedOrder.receiver_name}</div>
                  </div>
                )}
                {selectedOrder.receiver_phone && (
                  <div>
                    <div className="text-xs text-gray-500 mb-1">联系电话</div>
                    <div className="font-mono text-sm text-gray-700">{selectedOrder.receiver_phone}</div>
                  </div>
                )}
                {selectedOrder.receiver_address && (
                  <div>
                    <div className="text-xs text-gray-500 mb-1">收货地址</div>
                    <div className="text-sm text-gray-700">{selectedOrder.receiver_address}</div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </Modal>
      )}

      {/* Import Modal - 使用 Modal */}
      {showImportModal && (
        <Modal
          isOpen={showImportModal}
          onClose={() => setShowImportModal(false)}
          title="插入订单"
          footer={
            <div className="flex gap-3 w-full">
              <button
                onClick={() => setShowImportModal(false)}
                className="flex-1 px-6 py-3 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-800 font-bold transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleImportOrders}
                disabled={!importFile}
                className="flex-1 px-6 py-3 rounded-xl ios-btn-primary font-bold shadow-lg shadow-yellow-200 disabled:opacity-50"
              >
                导入订单
              </button>
            </div>
          }
        >
          <div className="space-y-5">
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-2">选择Excel文件</label>
              <input
                type="file"
                aria-label="选择Excel文件"
                accept=".xlsx,.xls"
                onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                className="w-full ios-input px-4 py-3 rounded-xl text-sm"
              />
              <p className="text-xs text-gray-500 mt-2">支持 .xlsx 和 .xls 格式</p>
            </div>

            {importFile && (
              <div className="p-3 bg-blue-50 rounded-xl">
                <div className="flex items-center gap-2">
                  <Upload className="w-4 h-4 text-blue-600" />
                  <span className="text-sm font-medium text-blue-900">{importFile.name}</span>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Ship Modal - 发货方式选择 */}
      {showShipModal && (
        <Modal
          isOpen={showShipModal}
          onClose={() => { setShowShipModal(false); setShipResult(null); }}
          title="立即发货"
          size="sm"
          footer={
            <button
              onClick={() => { setShowShipModal(false); setShipResult(null); }}
              className="w-full px-6 py-3 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-800 font-bold transition-colors"
            >
              {shipResult?.success ? '完成' : '取消'}
            </button>
          }
        >
          <div className="space-y-4">
            <p className="text-sm text-gray-600">请选择发货方式：</p>

            {/* 选项A: 仅修改发货状态 */}
            <button
              onClick={() => executeShip('status_only')}
              disabled={shipLoading}
              className="w-full text-left p-4 rounded-xl border-2 border-gray-200 hover:border-gray-400 hover:bg-gray-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Truck className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <div className="font-bold text-gray-900 text-sm">仅修改闲鱼发货状态</div>
                  <div className="text-xs text-gray-500 mt-1 leading-relaxed">
                    不实际扣除或发送卡券，仅在闲鱼平台将订单标记为"已发货"。
                    适用于已经给客户发过货、只是忘记在闲鱼修改状态的情况。
                  </div>
                </div>
              </div>
            </button>

            {/* 选项B: 完整发货流程 */}
            <button
              onClick={() => executeShip('full_delivery')}
              disabled={shipLoading}
              className="w-full text-left p-4 rounded-xl border-2 border-gray-200 hover:border-[#FFE815] hover:bg-yellow-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-yellow-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <PackageCheck className="w-5 h-5 text-yellow-700" />
                </div>
                <div>
                  <div className="font-bold text-gray-900 text-sm">完整发货（匹配卡券并发送）</div>
                  <div className="text-xs text-gray-500 mt-1 leading-relaxed">
                    自动匹配发货规则、获取卡券、发送卡券信息给买家，并修改发货状态。
                    适用于订单既没有发送卡券给买家、也没有修改发货状态的情况。
                  </div>
                </div>
              </div>
            </button>

            {/* 加载状态 */}
            {shipLoading && (
              <div className="flex items-center justify-center gap-2 py-3">
                <RefreshCw className="w-4 h-4 animate-spin text-gray-500" />
                <span className="text-sm text-gray-500">正在处理中...</span>
              </div>
            )}

            {/* 结果显示 */}
            {shipResult && (
              <div className={`p-3 rounded-xl text-sm ${shipResult.success ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
                {shipResult.success ? '✓ ' : '✗ '}{shipResult.message}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Edit Modal - 使用 Modal */}
      {showEditModal && editingOrder && (
        <Modal
          isOpen={showEditModal}
          onClose={() => setShowEditModal(false)}
          title="编辑订单"
          size="lg"
          footer={
            <div className="flex gap-3 w-full">
              <button
                onClick={() => setShowEditModal(false)}
                className="flex-1 px-6 py-3 rounded-xl font-bold bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                className="flex-1 ios-btn-primary px-6 py-3 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                <Save className="w-4 h-4" />
                保存更改
              </button>
            </div>
          }
        >
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">订单号</label>
                <input
                  type="text"
                  aria-label="订单号"
                  value={editingOrder.order_id}
                  disabled
                  className="w-full ios-input px-4 py-3 rounded-xl bg-gray-50 text-gray-500"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">订单状态</label>
                <select
                  value={editingOrder.status}
                  onChange={(e) => setEditingOrder({ ...editingOrder, status: e.target.value as OrderStatus })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                >
                  <option value="processing">处理中</option>
                  <option value="pending_ship">待发货</option>
                  <option value="shipped">已发货</option>
                  <option value="completed">已完成</option>
                  <option value="cancelled">已取消</option>
                  <option value="refunding">退款中</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">买家ID</label>
                <input
                  type="text"
                  aria-label="买家ID"
                  value={editingOrder.buyer_id}
                  onChange={(e) => setEditingOrder({ ...editingOrder, buyer_id: e.target.value })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">实付金额</label>
                <input
                  type="number"
                  aria-label="实付金额"
                  inputMode="numeric"
                  value={editingOrder.amount}
                  onChange={(e) => setEditingOrder({ ...editingOrder, amount: String(parseFloat(e.target.value) || 0) })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">收货人</label>
                <input
                  type="text"
                  aria-label="收货人"
                  value={editingOrder.receiver_name || ''}
                  onChange={(e) => setEditingOrder({ ...editingOrder, receiver_name: e.target.value })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">联系电话</label>
                <input
                  type="text"
                  aria-label="联系电话"
                  inputMode="tel"
                  value={editingOrder.receiver_phone || ''}
                  onChange={(e) => setEditingOrder({ ...editingOrder, receiver_phone: e.target.value })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-bold text-gray-700 mb-2">收货地址</label>
              <textarea
                value={editingOrder.receiver_address || ''}
                onChange={(e) => setEditingOrder({ ...editingOrder, receiver_address: e.target.value })}
                rows={2}
                className="w-full ios-input px-4 py-3 rounded-xl resize-none"
              />
            </div>

            <div>
              <label className="block text-sm font-bold text-gray-700 mb-2">商品标题</label>
              <input
                type="text"
                aria-label="商品标题"
                value={editingOrder.item_title || ''}
                onChange={(e) => setEditingOrder({ ...editingOrder, item_title: e.target.value })}
                className="w-full ios-input px-4 py-3 rounded-xl"
              />
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default OrderList;
