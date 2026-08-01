import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/static/',
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/cookies': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/qr-login': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/keywords': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/keywords-with-item-id': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/items': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/cards': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/delivery-rules': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/ai-reply-settings': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/system-settings': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/admin': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/analytics': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/verify': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/kb': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  build: {
    outDir: '../static',
    sourcemap: false, // 生产构建关闭 sourcemap，减小体积、避免源码泄露
    rollupOptions: {
      output: {
        // 手动分块：将 react/react-dom 抽 vendor chunk，业务组件按域分组
        manualChunks: {
          // React 核心：稳定不变，单独缓存
          'vendor-react': ['react', 'react-dom'],
          // 图标库：体积较大，独立分块
          'vendor-icons': ['lucide-react'],
        },
      },
    },
    emptyOutDir: false,
    // 大于 1MB 的资源警告阈值
    chunkSizeWarningLimit: 1024,
  },
});
