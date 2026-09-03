/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy:   { 50:'#f1f5f9',100:'#e2e8f0',200:'#cbd5e1',300:'#94a3b8',
                  600:'#334e68',700:'#243b53',800:'#182f45',900:'#102a43',950:'#0a1c2e' },
        danger: { 50:'#fef2f2',100:'#fee2e2',200:'#fecaca',500:'#ef4444',600:'#dc2626',700:'#b91c1c' },
        warn:   { 50:'#fffbeb',100:'#fef3c7',200:'#fde68a',500:'#f59e0b',600:'#d97706',700:'#b45309' },
        safe:   { 50:'#f0fdf4',100:'#dcfce7',200:'#bbf7d0',500:'#22c55e',600:'#16a34a',700:'#15803d' },
        info:   { 50:'#eff6ff',100:'#dbeafe',200:'#bfdbfe',500:'#3b82f6',600:'#2563eb',700:'#1d4ed8' },
      },
      fontFamily: {
        sans: ['Inter','Segoe UI','system-ui','-apple-system','sans-serif'],
        mono: ['ui-monospace','SFMono-Regular','Consolas','monospace'],
      },
      boxShadow: { card: '0 1px 2px 0 rgb(16 42 67 / 0.05), 0 1px 3px 0 rgb(16 42 67 / 0.06)' },
    },
  },
  plugins: [],
}
