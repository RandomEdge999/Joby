/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F6F7F9",
        surface: "#FFFFFF",
        ink: {
          900: "#0F1422",
          700: "#2A2F3E",
          500: "#5A6072",
          400: "#8A90A2",
          300: "#B6BBCA",
        },
        brand: {
          50:  "#EEF6FF",
          100: "#D9ECFF",
          200: "#B9DBFF",
          300: "#86C1FF",
          400: "#4C9CF6",
          500: "#256FE6",
          600: "#1D57C7",
          700: "#1D469B",
        },
        sky:    { 50: "#EAF6FB", 100: "#D6EEF7", 200: "#BCE1EF" },
        butter: { 50: "#FBF4E2", 100: "#F8EAC6", 200: "#F3DFA6" },
        mint:   { 50: "#E8F4EE", 100: "#D5EEE0" },
        rose:   { 50: "#FBEDEF", 100: "#F7D8DD" },
      },
      borderRadius: {
        xl: "14px",
        "2xl": "20px",
        "3xl": "28px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(15,20,34,0.04), 0 6px 20px -10px rgba(15,20,34,0.10)",
        ring: "0 0 0 1px rgba(15,20,34,0.05), 0 10px 30px -12px rgba(110,79,209,0.18)",
      },
    },
  },
  plugins: [],
};
