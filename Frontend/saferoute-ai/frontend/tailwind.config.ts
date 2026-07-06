import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F6F6F3",
        surface: "#FFFFFF",
        ink: "#14151A",
        muted: "#6B6F76",
        line: "#E7E7E3",
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
