/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        page: '#e2e8f0',
        card: '#f8fafc',
        accent: '#0f766e',
      },
    },
  },
  plugins: [],
}
