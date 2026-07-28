import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('应用异常捕获:', error, errorInfo);
  }

  handleReload = (): void => {
    window.location.reload();
  };

  handleGoHome = (): void => {
    window.location.href = '/';
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-[#F4F5F7] p-6">
          <div className="max-w-md w-full bg-white rounded-[2rem] shadow-xl p-8 text-center space-y-6">
            <div className="w-20 h-20 mx-auto rounded-full bg-amber-100 flex items-center justify-center">
              <AlertTriangle className="w-10 h-10 text-amber-500" />
            </div>
            <div className="space-y-2">
              <h1 className="text-2xl font-extrabold text-gray-900">页面出错了</h1>
              <p className="text-sm text-gray-500">
                很抱歉，页面遇到了一些问题。可以尝试重新加载，或返回首页继续操作。
              </p>
            </div>
            {this.state.error && (
              <details className="text-left bg-gray-50 rounded-xl p-3 text-xs text-gray-600 max-h-40 overflow-auto">
                <summary className="cursor-pointer font-bold text-gray-700">查看错误详情</summary>
                <pre className="mt-2 whitespace-pre-wrap break-all">
                  {this.state.error.toString()}
                  {this.state.errorInfo?.componentStack}
                </pre>
              </details>
            )}
            <div className="flex gap-3">
              <button
                onClick={this.handleGoHome}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-gray-100 hover:bg-gray-200 rounded-xl font-bold text-gray-700 transition-colors"
              >
                <Home className="w-4 h-4" />
                返回首页
              </button>
              <button
                onClick={this.handleReload}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-[#FFE815] hover:bg-yellow-300 rounded-xl font-bold text-black transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                重新加载
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
