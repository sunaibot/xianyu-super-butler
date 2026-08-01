import React, { useEffect, useState, useCallback } from 'react';
import {
  getKBScripts,
  createKBScript,
  updateKBScript,
  deleteKBScript,
  rebuildKBIndex,
  getKBStatus,
  searchKB,
  importKBCSV,
} from '../services/api';
import {
  Plus,
  Search,
  Edit,
  Trash2,
  Save,
  RefreshCw,
  Upload,
  BookOpen,
  FileText,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Search as SearchIcon,
} from 'lucide-react';
import { useToast } from './Toast';
import { useConfirm } from '../hooks/useConfirm';
import { useDebounce } from '../hooks/useDebounce';
import { usePagination } from '../hooks/usePagination';
import Modal from './ui/Modal';

interface KBScript {
  id: number;
  user_question: string;
  answer: string;
  intent_l1?: string;
  intent_l2?: string;
  enabled?: boolean;
  created_at?: string;
}

interface KBStatus {
  total_scripts: number;
  search_mode?: string;
}

interface SearchResult {
  id: number;
  document: string;
  metadata: { answer: string; intent_l1?: string; intent_l2?: string };
  similarity: number;
}

const KnowledgeBase: React.FC = () => {
  const [scripts, setScripts] = useState<KBScript[]>([]);
  const [total, setTotal] = useState(0);
  // 使用统一的 usePagination hook（替代手写 page 状态，支持 functional updater）
  const { page, totalPages, setPage, setTotalPages } = usePagination(1, 1);
  const [pageSize] = useState(20);
  const [searchInput, setSearchInput] = useState('');
  // 使用统一的 useDebounce hook：输入停止 300ms 后自动触发搜索
  const search = useDebounce(searchInput, 300);

  const [status, setStatus] = useState<KBStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [selectedScript, setSelectedScript] = useState<KBScript | null>(null);

  const [addForm, setAddForm] = useState({
    user_question: '',
    answer: '',
    intent_l1: '',
    intent_l2: '',
  });

  const [editForm, setEditForm] = useState({
    user_question: '',
    answer: '',
    intent_l1: '',
    intent_l2: '',
  });

  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [csvContent, setCsvContent] = useState('');

  const { showToast } = useToast();
  const confirm = useConfirm();

  const loadScripts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getKBScripts(page, pageSize, search);
      setScripts(res.scripts || []);
      setTotal(res.total || 0);
      setTotalPages(res.total_pages || Math.max(1, Math.ceil((res.total || 0) / pageSize)));
    } catch (e) {
      showToast('error', '加载话术失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, showToast, setTotalPages]);

  const loadStatus = useCallback(async () => {
    try {
      const res = await getKBStatus();
      setStatus(res);
    } catch (e) {
      console.error('Failed to load KB status:', e);
    }
  }, []);

  useEffect(() => {
    loadScripts();
  }, [loadScripts]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  // 搜索框输入变化时，重置到第一页（debounce 后会自动触发 loadScripts）
  useEffect(() => {
    setPage(1);
  }, [search, setPage]);

  const handleSearch = () => {
    // 兼容旧按钮：直接触发（debounce 已实现自动触发，此函数保留为显式入口）
    setPage(1);
  };

  const handleAdd = async () => {
    if (!addForm.user_question.trim() || !addForm.answer.trim()) {
      showToast('error', '问题和回复不能为空');
      return;
    }
    try {
      await createKBScript(addForm);
      showToast('success', '添加成功');
      setShowAddModal(false);
      setAddForm({ user_question: '', answer: '', intent_l1: '', intent_l2: '' });
      loadScripts();
      loadStatus();
    } catch (e) {
      showToast('error', '添加失败');
    }
  };

  const handleEdit = (script: KBScript) => {
    setSelectedScript(script);
    setEditForm({
      user_question: script.user_question,
      answer: script.answer,
      intent_l1: script.intent_l1,
      intent_l2: script.intent_l2,
    });
    setShowEditModal(true);
  };

  const handleUpdate = async () => {
    if (!selectedScript) return;
    if (!editForm.user_question.trim() || !editForm.answer.trim()) {
      showToast('error', '问题和回复不能为空');
      return;
    }
    try {
      await updateKBScript(selectedScript.id, editForm);
      showToast('success', '更新成功');
      setShowEditModal(false);
      loadScripts();
    } catch (e) {
      showToast('error', '更新失败');
    }
  };

  const handleDelete = async (id: number) => {
    if (!(await confirm({ title: '确认删除话术', content: '确定删除该话术吗？此操作不可恢复。', variant: 'danger' }))) return;
    try {
      await deleteKBScript(id);
      showToast('success', '删除成功');
      loadScripts();
      loadStatus();
    } catch (e) {
      showToast('error', '删除失败');
    }
  };

  const handleRebuild = async () => {
    if (!(await confirm({ title: '确认重建向量索引', content: '确定重建向量索引吗？这可能需要一些时间。' }))) return;
    try {
      const res = await rebuildKBIndex();
      showToast('success', res.message || '重建成功');
      loadStatus();
    } catch (e) {
      showToast('error', '重建失败');
    }
  };

  const handleSearchKB = async () => {
    if (!searchQuery.trim()) {
      showToast('error', '请输入搜索内容');
      return;
    }
    try {
      const res = await searchKB(searchQuery, 5);
      setSearchResults(res.results || []);
    } catch (e) {
      showToast('error', '搜索失败');
    }
  };

  const handleImport = async () => {
    if (!csvContent.trim()) {
      showToast('error', '请输入CSV内容');
      return;
    }
    try {
      const res = await importKBCSV(csvContent);
      showToast('success', res.message || '导入成功');
      setShowImportModal(false);
      setCsvContent('');
      loadScripts();
      loadStatus();
    } catch (e) {
      showToast('error', '导入失败');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-extrabold text-gray-900 flex items-center gap-3">
            <BookOpen className="w-8 h-8 text-[#FFE815]" />
            话术库管理
          </h1>
          <p className="text-gray-500 mt-1">管理 AI 客服话术，支持 RAG 智能检索</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSearchModal(true)}
            className="px-4 py-2.5 bg-white border border-gray-200 rounded-xl font-medium text-gray-700 hover:bg-gray-50 transition-colors flex items-center gap-2"
          >
            <SearchIcon className="w-4 h-4" />
            测试检索
          </button>
          <button
            onClick={() => setShowImportModal(true)}
            className="px-4 py-2.5 bg-white border border-gray-200 rounded-xl font-medium text-gray-700 hover:bg-gray-50 transition-colors flex items-center gap-2"
          >
            <Upload className="w-4 h-4" />
            CSV导入
          </button>
          <button
            onClick={handleRebuild}
            className="px-4 py-2.5 bg-white border border-gray-200 rounded-xl font-medium text-gray-700 hover:bg-gray-50 transition-colors flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            重建索引
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-5 py-2.5 bg-[#FFE815] hover:bg-yellow-300 rounded-xl font-bold text-black transition-colors flex items-center gap-2 shadow-lg shadow-yellow-100"
          >
            <Plus className="w-4 h-4" />
            添加话术
          </button>
        </div>
      </div>

      {status && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm">
            <div className="flex items-center gap-2 text-gray-500 text-sm">
              <FileText className="w-4 h-4" />
              <span>话术总数</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 mt-1">{status.total_scripts}</div>
          </div>
          <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm">
            <div className="flex items-center gap-2 text-gray-500 text-sm">
              <Sparkles className="w-4 h-4" />
              <span>检索模式</span>
            </div>
            <div className="text-lg font-bold text-gray-900 mt-1">
              关键词匹配
            </div>
          </div>
          <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm">
            <div className="flex items-center gap-2 text-gray-500 text-sm">
              <BookOpen className="w-4 h-4" />
              <span>搜索模式</span>
            </div>
            <div className="text-sm font-bold text-gray-900 mt-1 truncate">{status.search_mode || 'keyword_match'}</div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm">
        <div className="p-5 border-b border-gray-100 flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              aria-label="搜索话术内容"
              inputMode="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="搜索话术内容..."
              className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none"
            />
          </div>
          <button
            onClick={handleSearch}
            className="px-4 py-2.5 bg-gray-100 hover:bg-gray-200 rounded-xl font-medium text-gray-700 transition-colors"
          >
            搜索
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 text-left text-gray-500 text-sm font-medium">
                <th className="px-5 py-3">ID</th>
                <th className="px-5 py-3">用户问题</th>
                <th className="px-5 py-3">AI回复</th>
                <th className="px-5 py-3">意图分类</th>
                <th className="px-5 py-3">更新时间</th>
                <th className="px-5 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-gray-500">
                    加载中...
                  </td>
                </tr>
              ) : scripts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-gray-500">
                    暂无话术，点击"添加话术"开始创建
                  </td>
                </tr>
              ) : (
                scripts.map((script) => (
                  <tr key={script.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-3 text-gray-500 text-sm">{script.id}</td>
                    <td className="px-5 py-3 text-gray-900 max-w-xs truncate" title={script.user_question}>
                      {script.user_question}
                    </td>
                    <td className="px-5 py-3 text-gray-600 max-w-md truncate" title={script.answer}>
                      {script.answer}
                    </td>
                    <td className="px-5 py-3">
                      {script.intent_l1 && (
                        <span className="inline-block px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full mr-1">
                          {script.intent_l1}
                        </span>
                      )}
                      {script.intent_l2 && (
                        <span className="inline-block px-2 py-0.5 bg-purple-50 text-purple-600 text-xs rounded-full">
                          {script.intent_l2}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-gray-500 text-sm">
                      {new Date(script.created_at).toLocaleString('zh-CN')}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleEdit(script)}
                          className="p-2 text-blue-500 hover:bg-blue-50 rounded-lg transition-colors"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(script.id)}
                          className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="p-4 border-t border-gray-100 flex items-center justify-between">
            <span className="text-sm text-gray-500">
              共 {total} 条，第 {page}/{totalPages} 页
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="添加话术"
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowAddModal(false)}
              className="px-5 py-2.5 rounded-xl font-medium text-gray-700 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              onClick={handleAdd}
              className="px-5 py-2.5 bg-[#FFE815] hover:bg-yellow-300 rounded-xl font-bold text-black flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              保存
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">用户问题 *</label>
            <textarea
              value={addForm.user_question}
              onChange={(e) => setAddForm({ ...addForm, user_question: e.target.value })}
              placeholder="输入买家可能提出的问题..."
              className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none resize-none"
              rows={3}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">AI回复 *</label>
            <textarea
              value={addForm.answer}
              onChange={(e) => setAddForm({ ...addForm, answer: e.target.value })}
              placeholder="输入针对该问题的回复..."
              className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none resize-none"
              rows={4}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">一级意图</label>
              <input
                type="text"
                aria-label="一级意图"
                value={addForm.intent_l1}
                onChange={(e) => setAddForm({ ...addForm, intent_l1: e.target.value })}
                placeholder="如：议价"
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">二级意图</label>
              <input
                type="text"
                aria-label="二级意图"
                value={addForm.intent_l2}
                onChange={(e) => setAddForm({ ...addForm, intent_l2: e.target.value })}
                placeholder="如：首次议价"
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none"
              />
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={showEditModal && !!selectedScript}
        onClose={() => setShowEditModal(false)}
        title={selectedScript ? `编辑话术 #${selectedScript.id}` : '编辑话术'}
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowEditModal(false)}
              className="px-5 py-2.5 rounded-xl font-medium text-gray-700 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              onClick={handleUpdate}
              className="px-5 py-2.5 bg-[#FFE815] hover:bg-yellow-300 rounded-xl font-bold text-black flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              保存
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">用户问题 *</label>
            <textarea
              value={editForm.user_question}
              onChange={(e) => setEditForm({ ...editForm, user_question: e.target.value })}
              className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none resize-none"
              rows={3}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">AI回复 *</label>
            <textarea
              value={editForm.answer}
              onChange={(e) => setEditForm({ ...editForm, answer: e.target.value })}
              className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none resize-none"
              rows={4}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">一级意图</label>
              <input
                type="text"
                aria-label="一级意图"
                value={editForm.intent_l1}
                onChange={(e) => setEditForm({ ...editForm, intent_l1: e.target.value })}
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">二级意图</label>
              <input
                type="text"
                aria-label="二级意图"
                value={editForm.intent_l2}
                onChange={(e) => setEditForm({ ...editForm, intent_l2: e.target.value })}
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none"
              />
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={showSearchModal}
        onClose={() => setShowSearchModal(false)}
        title="检索测试"
        size="md"
      >
        <div className="space-y-4">
          <div className="flex gap-3">
            <input
              type="text"
              aria-label="输入要测试的问题"
              inputMode="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearchKB()}
              placeholder="输入要测试的问题..."
              className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none"
            />
            <button
              onClick={handleSearchKB}
              className="px-5 py-2.5 bg-[#FFE815] hover:bg-yellow-300 rounded-xl font-bold text-black"
            >
              检索
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="space-y-3">
              <div className="text-sm font-medium text-gray-700">检索结果 (Top {searchResults.length})</div>
              {searchResults.map((result, i) => (
                <div key={i} className="p-4 bg-gray-50 rounded-xl border border-gray-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-900">#{i + 1} {result.document}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      result.similarity >= 75 ? 'bg-green-100 text-green-600' :
                      result.similarity >= 50 ? 'bg-yellow-100 text-yellow-600' :
                      'bg-gray-100 text-gray-500'
                    }`}>
                      相似度 {result.similarity}%
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">{result.metadata.answer}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <Modal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        title="CSV 批量导入"
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowImportModal(false)}
              className="px-5 py-2.5 rounded-xl font-medium text-gray-700 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              onClick={handleImport}
              className="px-5 py-2.5 bg-[#FFE815] hover:bg-yellow-300 rounded-xl font-bold text-black flex items-center gap-2"
            >
              <Upload className="w-4 h-4" />
              导入
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="text-sm text-gray-500">
            CSV格式：<code className="bg-gray-100 px-2 py-0.5 rounded">question,answer,intent_l1,intent_l2</code>
          </div>
          <textarea
            value={csvContent}
            onChange={(e) => setCsvContent(e.target.value)}
            placeholder="question,answer,intent_l1,intent_l2&#10;你好,您好在的哦～,问候,&#10;多少钱,价格面议哈,议价,首次议价"
            className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100 outline-none resize-none font-mono text-sm"
            rows={10}
          />
        </div>
      </Modal>
    </div>
  );
};

export default KnowledgeBase;
