/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: 'rgb(var(--bg) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        'surface-2': 'rgb(var(--surface-2) / <alpha-value>)',
        'surface-3': 'rgb(var(--surface-3) / <alpha-value>)',
        border: 'rgb(var(--border) / <alpha-value>)',
        'border-strong': 'rgb(var(--border-strong) / <alpha-value>)',
        text: 'rgb(var(--text) / <alpha-value>)',
        'text-2': 'rgb(var(--text-2) / <alpha-value>)',
        'text-3': 'rgb(var(--text-3) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        'accent-dim': 'rgb(var(--accent) / 0.14)',
        success: 'rgb(var(--success) / <alpha-value>)',
        warning: 'rgb(var(--warning) / <alpha-value>)',
        danger: 'rgb(var(--danger) / <alpha-value>)',
        'trk-system': 'rgb(var(--trk-system) / <alpha-value>)',
        'trk-app': 'rgb(var(--trk-app) / <alpha-value>)',
        'trk-mic': 'rgb(var(--trk-mic) / <alpha-value>)',
        'trk-device': 'rgb(var(--trk-device) / <alpha-value>)',
        'trk-imported': 'rgb(var(--trk-imported) / <alpha-value>)',
      }
    },
  },
  plugins: [],
}
