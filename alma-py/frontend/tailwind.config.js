/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#070b14', 900: '#0b1220', 800: '#111a2e', 700: '#18233d', 600: '#22304f' },
        brand: { 300: '#7ee7d7', 400: '#2dd4bf', 500: '#14b8a6', 600: '#0d9488', 700: '#0f766e' },
        sand: { 50: '#faf8f3', 100: '#f3efe6', 200: '#e7e0d0' },
        gold: { 400: '#f2c14e', 500: '#e0a82e' },
      },
      fontFamily: {
        display: ['"Iowan Old Style"', '"Palatino Linotype"', 'Palatino', 'Georgia', 'serif'],
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      keyframes: {
        rise: { '0%': { opacity: 0, transform: 'translateY(14px)' }, '100%': { opacity: 1, transform: 'none' } },
        tick: { '0%': { opacity: 0, transform: 'scale(.6)' }, '100%': { opacity: 1, transform: 'scale(1)' } },
        pulseRing: { '0%': { boxShadow: '0 0 0 0 rgba(45,212,191,.5)' }, '100%': { boxShadow: '0 0 0 14px rgba(45,212,191,0)' } },
        drift: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-8px)' } },
      },
      animation: { rise: 'rise .6s ease both', tick: 'tick .35s ease both', pulseRing: 'pulseRing 1.8s infinite', drift: 'drift 6s ease-in-out infinite' },
    },
  },
  plugins: [],
}
