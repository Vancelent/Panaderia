/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      colors: {
        // Tonos de corteza horneada
        brand: {
          50: '#fdf8f0', 100: '#f9ecd8', 200: '#f2d5ac', 300: '#e9b877', 400: '#df9546',
          500: '#d67a27', 600: '#c2611d', 700: '#a1491a', 800: '#823b1c', 900: '#6a321a', 950: '#3a170b',
        },
      },
      keyframes: {
        'fade-in': { from: { opacity: 0 }, to: { opacity: 1 } },
        'slide-up': { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'none' } },
      },
      animation: {
        'fade-in': 'fade-in 120ms ease-out',
        'slide-up': 'slide-up 160ms ease-out',
      },
    },
  },
  plugins: [],
}
