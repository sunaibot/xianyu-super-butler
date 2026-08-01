import React, { useState, useEffect } from 'react';
import { getAllUsers, deleteUser, changeAdminPassword } from '../services/api';
import { UserInfo } from '../types';
import Modal from './ui/Modal';
import { Trash2, Key, Shield, Loader2, AlertTriangle, Save } from 'lucide-react';

const Users: React.FC = () => {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserInfo | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await getAllUsers();
      setUsers(data);
    } catch (err) {
      setMessage({ type: 'error', text: '加载用户列表失败' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const showMsg = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await deleteUser(deleteTarget.id);
      if (res.success !== false) {
        showMsg('success', `用户 ${deleteTarget.username} 已删除`);
        setUsers(prev => prev.filter(u => u.id !== deleteTarget.id));
      } else {
        showMsg('error', res.message || '删除失败');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '删除失败';
      showMsg('error', msg);
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

  const handleSavePassword = async () => {
    if (!currentPassword || !newPassword) {
      showMsg('error', '请填写完整密码信息');
      return;
    }
    if (newPassword !== confirmPassword) {
      showMsg('error', '两次输入的新密码不一致');
      return;
    }
    if (newPassword.length < 6) {
      showMsg('error', '新密码至少6位');
      return;
    }
    setSavingPassword(true);
    try {
      const res = await changeAdminPassword(currentPassword, newPassword);
      if (res.success !== false) {
        showMsg('success', '密码修改成功');
        setShowPasswordModal(false);
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } else {
        showMsg('error', res.message || '密码修改失败');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '密码修改失败';
      showMsg('error', msg);
    } finally {
      setSavingPassword(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in pb-20">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-extrabold text-gray-900">用户管理</h2>
          <p className="text-gray-500 mt-2 font-medium">管理系统用户账号与权限。</p>
        </div>
        <button
          onClick={() => setShowPasswordModal(true)}
          className="ios-btn-primary px-5 py-3 rounded-2xl text-sm font-bold flex items-center gap-2 shadow-lg shadow-yellow-200"
        >
          <Key className="w-4 h-4" /> 修改管理员密码
        </button>
      </div>

      {message && (
        <div className={`p-4 rounded-2xl font-bold text-sm flex items-center gap-2 ${
          message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
        }`}>
          {message.type === 'success' ? '✓' : '⚠'} {message.text}
        </div>
      )}

      <div className="ios-card bg-white rounded-[2rem] p-6 min-h-[400px]">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> 加载中...
          </div>
        ) : (
          <div className="space-y-3">
            {users.length === 0 ? (
              <div className="text-center py-20 text-gray-400">暂无用户</div>
            ) : (
              users.map(user => (
                <div
                  key={user.id}
                  className="flex items-center justify-between p-5 rounded-2xl border border-gray-100 bg-[#F7F8FA] hover:bg-white hover:shadow-lg transition-all duration-300"
                >
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center font-bold text-lg ${
                      user.is_admin ? 'bg-black text-[#FFE815]' : 'bg-gray-200 text-gray-600'
                    }`}>
                      {user.username.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-bold text-gray-900 text-lg">{user.username}</h3>
                        {user.is_admin && (
                          <span className="px-2 py-0.5 bg-yellow-100 text-yellow-800 text-xs font-bold rounded-lg flex items-center gap-1">
                            <Shield className="w-3 h-3" /> 管理员
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-500 mt-1">
                        ID: {user.id}
                        {user.last_login && <span className="ml-3">最后登录: {user.last_login}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {user.username === 'admin' ? (
                      <span className="text-xs text-gray-400 font-medium">默认管理员，不可删除</span>
                    ) : (
                      <button
                        onClick={() => setDeleteTarget(user)}
                        className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-colors"
                        title="删除用户"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Change Password Modal */}
      <Modal
        isOpen={showPasswordModal}
        onClose={() => setShowPasswordModal(false)}
        title="修改管理员密码"
        size="sm"
        footer={
          <div className="flex gap-3">
            <button
              onClick={() => setShowPasswordModal(false)}
              className="flex-1 px-6 py-3 rounded-xl font-bold bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSavePassword}
              disabled={savingPassword}
              className="flex-1 ios-btn-primary px-6 py-3 rounded-xl font-bold flex items-center justify-center gap-2 disabled:opacity-70"
            >
              {savingPassword ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {savingPassword ? '保存中...' : '保存修改'}
            </button>
          </div>
        }
      >
        <div className="space-y-5">
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">当前密码</label>
            <input
              type="password"
              aria-label="当前密码"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="输入当前密码"
              className="w-full ios-input px-4 py-3 rounded-xl"
            />
          </div>
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">新密码</label>
            <input
              type="password"
              aria-label="新密码"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="至少6位字符"
              className="w-full ios-input px-4 py-3 rounded-xl"
            />
          </div>
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">确认新密码</label>
            <input
              type="password"
              aria-label="确认新密码"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="再次输入新密码"
              className="w-full ios-input px-4 py-3 rounded-xl"
            />
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="确认删除用户"
        size="sm"
        footer={
          <div className="flex gap-3">
            <button
              onClick={() => setDeleteTarget(null)}
              className="flex-1 px-6 py-3 rounded-xl font-bold bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="flex-1 px-6 py-3 rounded-xl font-bold bg-red-500 text-white hover:bg-red-600 transition-colors flex items-center justify-center gap-2 disabled:opacity-70"
            >
              {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
              {deleting ? '删除中...' : '确认删除'}
            </button>
          </div>
        }
      >
        <div className="space-y-5">
          <div className="flex items-center gap-3 p-4 bg-red-50 rounded-xl">
            <AlertTriangle className="w-6 h-6 text-red-500" />
            <div className="text-sm text-red-700">
              确定要删除用户 <strong>{deleteTarget?.username}</strong> 吗？此操作不可恢复。
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Users;
