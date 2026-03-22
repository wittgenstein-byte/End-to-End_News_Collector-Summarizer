/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./**/*.{html,js}"],
  theme: {
    extend: {
      colors: {
        "primary": "#2e4d83",
        "on-primary": "#ffffff",
        "surface": "#fef9f0",
        "on-surface": "#1d1c16",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#f8f3ea",
        "surface-container": "#f2ede4",
        "surface-container-high": "#ece8df",
        "surface-container-highest": "#e7e2d9",
        "outline": "#747780",
        "outline-variant": "#c4c6d1",
        "secondary": "#545e76",
        "secondary-container": "#d5dffb",
        "on-secondary-container": "#58637a",
        "error": "#ba1a1a",
      },
      fontFamily: {
        "headline": ["Newsreader", "serif"],
        "body": ["Manrope", "sans-serif"],
        "label": ["Manrope", "sans-serif"]
      },
      borderRadius: {
        "DEFAULT": "0.125rem", 
        "lg": "0.25rem", 
        "xl": "0.5rem", 
        "full": "0.75rem"
      },
      animation: {
        'marquee': 'marquee 40s linear infinite',
      },
      keyframes: {
        marquee: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        }
      }
    },
  },
  plugins: [],
}
