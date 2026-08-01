/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./contexts/**/*.{js,ts,jsx,tsx}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      screens: {
        // 移动优先断点约定
        sm: '640px',   // 大屏手机
        md: '768px',   // 平板 / 小笔记本（移动端→桌面端切换点）
        lg: '1024px',  // 笔记本
        xl: '1280px',  // 桌面
      },
      colors: {
        brand: {
          DEFAULT: '#FFE815',
          dark: '#FFD600',
          light: '#FFF6B0',
        },
      },
      borderRadius: {
        '2xl': '1.5rem',
        '3xl': '2rem',
      },
      spacing: {
        // iOS 安全区适配
        'safe-top': 'env(safe-area-inset-top)',
        'safe-bottom': 'env(safe-area-inset-bottom)',
        'safe-left': 'env(safe-area-inset-left)',
        'safe-right': 'env(safe-area-inset-right)',
        // 底部 TabBar 高度（含安全区）
        'tabbar': 'calc(4rem + env(safe-area-inset-bottom))',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          '"Helvetica Neue"',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
      },
      zIndex: {
        'tabbar': '60',
        'drawer': '70',
        'topbar': '50',
      },
    },
  },
  plugins: [],
}
