import React, { useState, useEffect, Suspense, lazy } from 'react';
import Sidebar from './components/Sidebar';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import { WebSocketProvider, useWebSocketContext } from './contexts/WebSocketContext';
import { login, verifySession } from './services/api';
import { ShieldCheck, ArrowRight, Loader2, User, Lock, TerminalSquare, Wifi, WifiOff, Compass } from 'lucide-react';

// 路由级懒加载，减小首屏 bundle 体积
const Dashboard = lazy(() => import('./components/Dashboard'));
const AccountList = lazy(() => import('./components/AccountList'));
const OrderList = lazy(() => import('./components/OrderList'));
const CardList = lazy(() => import('./components/CardList'));
const ItemList = lazy(() => import('./components/ItemList'));
const Settings = lazy(() => import('./components/Settings'));
const Keywords = lazy(() => import('./components/Keywords'));
const Rules = lazy(() => import('./components/Rules'));
const Users = lazy(() => import('./components/Users'));

// 页面加载占位组件
const PageLoading: React.FC = () => (
  <div className="flex items-center justify-center h-64">
    <Loader2 className="w-8 h-8 text-[#FFE815] animate-spin" />
  </div>
);

// 404 页面
const NotFoundPage: React.FC = () => (
  <div className="flex flex-col items-center justify-center h-96 text-center space-y-4">
    <div className="w-20 h-20 rounded-full bg-amber-100 flex items-center justify-center">
      <Compass className="w-10 h-10 text-amber-500" />
    </div>
    <h1 className="text-3xl font-extrabold text-gray-900">页面不存在</h1>
    <p className="text-gray-500">你访问的页面可能已被移动或删除</p>
    <button
      onClick={() => window.location.reload()}
      className="px-6 py-2.5 bg-[#FFE815] hover:bg-yellow-300 rounded-xl font-bold text-black transition-colors"
    >
      返回首页
    </button>
  </div>
);

const App: React.FC = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [needsInit, setNeedsInit] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  // Check auth on mount
  useEffect(() => {
      verifySession()
        .then((res) => {
          if (res?.initialized === false) {
            setNeedsInit(true);
            setIsLoggedIn(false);
            return;
          }

          setNeedsInit(false);
          if (res?.authenticated) setIsLoggedIn(true);
        })
        .catch(() => setIsLoggedIn(false))
        .finally(() => setCheckingAuth(false));

      const handleLogout = () => setIsLoggedIn(false);
      window.addEventListener('auth:logout', handleLogout);
      return () => window.removeEventListener('auth:logout', handleLogout);
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
      e.preventDefault();
      setLoginLoading(true);
      setLoginError('');
      
      try {
          const res = await login({ username, password });
          if (res.success) {
              setIsLoggedIn(true);
          } else {
              setLoginError(res.message || '登录失败');
          }
      } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          setLoginError(msg || '登录失败');
      } finally {
          setLoginLoading(false);
      }
  };


  if (checkingAuth) {
      return (
          <div className="min-h-screen flex items-center justify-center bg-[#f5f5f7]">
              <Loader2 className="w-8 h-8 text-[#FFE815] animate-spin" />
          </div>
      );
  }

  // Init Screen (system not initialized)
  if (needsInit) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F4F5F7] p-4 relative overflow-hidden font-sans">
        <div className="absolute top-[-10%] left-[-10%] w-[60%] h-[60%] bg-yellow-200/40 rounded-full blur-[120px] animate-pulse"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[60%] bg-blue-200/30 rounded-full blur-[120px] animate-pulse" style={{animationDelay: '2s'}}></div>

        <div className="bg-white/80 backdrop-blur-3xl p-8 md:p-12 rounded-[3rem] shadow-[0_20px_60px_-15px_rgba(0,0,0,0.05)] w-full max-w-xl border border-white relative z-10 animate-fade-in">
          <div className="text-center mb-8">
            <div className="w-24 h-24 bg-[#FFE815] rounded-[2rem] flex items-center justify-center shadow-xl shadow-yellow-200 mx-auto mb-6 transform rotate-[-6deg] transition-all duration-500">
              <TerminalSquare className="w-10 h-10 text-black" />
            </div>
            <h2 className="text-3xl font-extrabold text-gray-900 mb-2 tracking-tight">系统尚未初始化</h2>
            <p className="text-gray-600 font-medium">为避免默认口令风险，管理员必须通过服务器本机 CLI 初始化。</p>
          </div>

          <div className="space-y-4">
            <div className="p-4 rounded-2xl bg-gray-50 border border-gray-100">
              <div className="text-sm font-bold text-gray-900 mb-2">请在服务器上执行：</div>
              <pre className="text-xs bg-black text-white p-4 rounded-2xl overflow-x-auto">python3 init_admin.py</pre>
              <div className="text-xs text-gray-500 mt-2">完成后刷新页面即可进入登录。</div>
            </div>

            <button
              type="button"
              onClick={() => window.location.reload()}
              className="w-full ios-btn-primary h-14 rounded-2xl text-lg shadow-xl shadow-yellow-200 mt-2 flex items-center justify-center gap-2 group"
            >
              我已初始化，刷新 <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
          </div>

          <div className="mt-8 pt-6 border-t border-gray-100 text-center">
            <span className="text-xs text-gray-400 font-medium tracking-widest uppercase">Secure Bootstrap</span>
          </div>
        </div>
      </div>
    );
  }

  // Login Screen Component
  if (!isLoggedIn) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F4F5F7] p-4 relative overflow-hidden font-sans">
        {/* Animated Background Blobs */}
        <div className="absolute top-[-10%] left-[-10%] w-[60%] h-[60%] bg-yellow-200/40 rounded-full blur-[120px] animate-pulse"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[60%] bg-blue-200/30 rounded-full blur-[120px] animate-pulse" style={{animationDelay: '2s'}}></div>

        <div className="bg-white/80 backdrop-blur-3xl p-8 md:p-12 rounded-[3rem] shadow-[0_20px_60px_-15px_rgba(0,0,0,0.05)] w-full max-w-lg border border-white relative z-10 animate-fade-in">
          
          {/* Header with Logo */}
          <div className="text-center mb-10">
             <div className="w-24 h-24 bg-[#FFE815] rounded-[2rem] flex items-center justify-center shadow-xl shadow-yellow-200 mx-auto mb-6 transform rotate-[-6deg] hover:rotate-0 transition-all duration-500 cursor-pointer group">
                <span className="text-black font-extrabold text-5xl group-hover:scale-110 transition-transform">闲</span>
             </div>
             <h2 className="text-3xl font-extrabold text-gray-900 mb-2 tracking-tight">欢迎回来</h2>
             <p className="text-gray-500 font-medium">闲鱼智能自动发货与管家系统</p>
          </div>
          
          <form onSubmit={handleLogin} className="space-y-5">
            <div className="space-y-4">
                <div className="relative group">
                    <User className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black transition-colors" />
                    <input 
                        type="text" 
                        placeholder="管理员账号" 
                        value={username}
                        onChange={e => setUsername(e.target.value)}
                        className="w-full ios-input pl-14 pr-6 py-4.5 rounded-2xl text-base h-14"
                    />
                </div>
                <div className="relative group">
                    <Lock className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black transition-colors" />
                    <input 
                        type="password" 
                        placeholder="密码" 
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        className="w-full ios-input pl-14 pr-6 py-4.5 rounded-2xl text-base h-14"
                    />
                </div>
            </div>
            
            {loginError && (
                <div className="p-3 rounded-xl bg-red-50 text-red-500 text-sm text-center font-bold flex items-center justify-center gap-2">
                    <ShieldCheck className="w-4 h-4" /> {loginError}
                </div>
            )}

            <button 
              type="submit" 
              disabled={loginLoading}
              className="w-full ios-btn-primary h-14 rounded-2xl text-lg shadow-xl shadow-yellow-200 mt-2 flex items-center justify-center gap-2 group disabled:opacity-70"
            >
              {loginLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <>立即登录 <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" /></>}
            </button>
          </form>
          
          <div className="mt-8 pt-6 border-t border-gray-100">
             <div className="mt-6 text-center">
                 <span className="text-xs text-gray-400 font-medium tracking-widest uppercase">
                    Xianyu Auto-Dispatch Pro v2.5
                 </span>
             </div>
          </div>
        </div>
      </div>
    );
  }

  // Main App Layout
  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard />;
      case 'accounts': return <AccountList />;
      case 'orders': return <OrderList />;
      case 'cards': return <CardList />;
      case 'items': return <ItemList />;
      case 'keywords': return <Keywords />;
      case 'rules': return <Rules />;
      case 'users': return <Users />;
      case 'settings': return <Settings />;
      default: return <NotFoundPage />;
    }
  };

  // WS Status Indicator (inner component)
  const WSStatusBar: React.FC = () => {
    const { connected } = useWebSocketContext();
    return (
      <div className="fixed top-4 right-4 z-[100] flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/80 backdrop-blur-xl shadow-md border border-gray-200 text-xs font-medium">
        {connected ? (
          <>
            <Wifi className="w-3.5 h-3.5 text-green-500" />
            <span className="text-green-700">实时连接</span>
          </>
        ) : (
          <>
            <WifiOff className="w-3.5 h-3.5 text-gray-400 animate-pulse" />
            <span className="text-gray-500">连接中...</span>
          </>
        )}
      </div>
    );
  };

  return (
    <ErrorBoundary>
    <ToastProvider>
    <WebSocketProvider>
    <div className="flex min-h-screen bg-[#F4F5F7] text-[#111]">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onLogout={() => {
            setIsLoggedIn(false);
        }}
      />

      <main className="flex-1 ml-64 p-8 md:p-12 overflow-y-auto h-screen relative scroll-smooth">
        {/* Subtle background decoration */}
        <div className="fixed top-0 right-0 w-[800px] h-[800px] bg-gradient-to-bl from-yellow-50 to-transparent rounded-full blur-[120px] pointer-events-none -z-10 opacity-60"></div>

        <WSStatusBar />

        <div className="max-w-[1400px] mx-auto pb-10">
            <ErrorBoundary>
              <Suspense fallback={<PageLoading />}>
                {renderContent()}
              </Suspense>
            </ErrorBoundary>
        </div>
      </main>
    </div>
    </WebSocketProvider>
    </ToastProvider>
    </ErrorBoundary>
  );
};

export default App;