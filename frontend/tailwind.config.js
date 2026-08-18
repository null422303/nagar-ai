/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
        night: { DEFAULT: '#0b1120', soft: '#111a30' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Space Grotesk"', 'Inter', 'sans-serif'],
      },
      boxShadow: {
        glass: '0 8px 32px rgba(2, 12, 36, 0.35)',
        glow: '0 0 24px rgba(99, 102, 241, 0.35)',
      },
    },
  },
  plugins: [],
}
