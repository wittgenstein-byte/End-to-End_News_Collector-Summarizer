/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./index.html", "./static/**/*.js"],
  theme: {
    extend: {
      colors: {
        "primary": "#1d3557",
        "primary-container": "#14253d",
        "on-primary": "#ffffff",
        "surface": "#f7f4ed",
        "on-surface": "#141413",
        "on-surface-variant": "#575652",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#f0ece1",
        "surface-container": "#e8e3d7",
        "surface-container-high": "#dfd9cb",
        "surface-container-highest": "#d5cfc0",
        "outline": "#78766f",
        "outline-variant": "#cbc7bc",
        "secondary": "#8c3b2b",
        "secondary-container": "#f9e3de",
        "on-secondary-container": "#5c2216",
        "error": "#b91c1c",
      },
      fontFamily: {
        "headline": ["Newsreader", "Noto Serif Thai", "serif"],
        "body": ["Bai Jamjuree", "sans-serif"],
        "label": ["JetBrains Mono", "Bai Jamjuree", "monospace"]
      },
      borderRadius: {
        "DEFAULT": "0.125rem",
        "lg": "0.25rem",
        "xl": "0.375rem",
        "2xl": "0.5rem",
        "full": "9999px"
      },
      animation: {
        "marquee": "marquee 45s linear infinite",
      },
      keyframes: {
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        }
      }
    },
  },
  plugins: [],
}