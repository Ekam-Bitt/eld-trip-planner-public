/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#0f172a" },
        secondary: { DEFAULT: "#1f2937" },
        accent: { DEFAULT: "#2563eb", 500: "#3b82f6", 600: "#2563eb" },
        danger: "#ef4444",
        success: "#22c55e",
        "text-light": "#f3f4f6",
        "text-muted": "#9ca3af",
      },
      borderRadius: {
        xl: "0.75rem",
        "2xl": "1rem",
      },
      boxShadow: {
        soft: "0 4px 12px rgba(0,0,0,0.25)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "Noto Sans",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
