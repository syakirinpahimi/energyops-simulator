import type { Config } from "tailwindcss";

// SCADA-inspired industrial palette. Original (no Schneider/Siemens/GE branding).
// Cool steel + amber accents with semantic alarm colours.
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        steel: {
          50: "#f4f6f8",
          100: "#dbe1e8",
          200: "#b9c4d0",
          300: "#8c9bad",
          400: "#5e6e82",
          500: "#3f4d60",
          600: "#2c384a",
          700: "#1f2937",
          800: "#141c28",
          900: "#0b1018",
          950: "#060a10",
        },
        signal: {
          run: "#22c55e",
          warn: "#f59e0b",
          fault: "#ef4444",
          offline: "#6b7280",
          info: "#38bdf8",
        },
        accent: {
          DEFAULT: "#f0a93b",
          dim: "#b87f24",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        panel:
          "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 0 0 1px rgba(255,255,255,0.04), 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};

export default config;
