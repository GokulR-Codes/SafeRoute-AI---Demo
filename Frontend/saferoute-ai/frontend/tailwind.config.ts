import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Semantic surface tokens are driven by CSS variables (see globals.css)
        // so they flip between light and dark. `<alpha-value>` keeps Tailwind
        // opacity modifiers like `bg-surface/95` working.
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        route: "#2FAE4E",
        source: "#2F6FED",
        danger: "#E1483C",
        risk: {
          low: "#2FAE4E",
          lowBg: "#E6F6EA",
          moderate: "#D98A16",
          moderateBg: "#FBEED4",
          high: "#E1483C",
          highBg: "#FAE4E2",
        },
      },
      fontFamily: {
        display: ["var(--font-space-grotesk)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
      },
      boxShadow: {
        floating: "0 12px 32px -8px rgba(20,21,26,0.16), 0 2px 8px -2px rgba(20,21,26,0.08)",
      },
      borderRadius: {
        card: "20px",
        pill: "999px",
      },
    },
  },
  plugins: [],
};

export default config;
