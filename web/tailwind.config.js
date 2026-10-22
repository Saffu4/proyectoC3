/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef7f1", 500: "#238636", 600: "#1d6f2c",
        },
      },
    },
  },
  plugins: [],
};
