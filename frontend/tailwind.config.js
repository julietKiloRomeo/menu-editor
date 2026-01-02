/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#631d76',
          surface: '#2e2532',
          dark: '#201a23',
          accent: '#9affc3',
        },
        danger: '#ff6b6b',
        muted: '#fbfbfb',
      },
      fontFamily: {
        display: ['\"Space Grotesk\"', 'Inter', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 20px 45px rgba(32, 26, 35, 0.35)',
      },
      borderRadius: {
        panel: '1.5rem',
      },
    },
  },
  plugins: [],
}
