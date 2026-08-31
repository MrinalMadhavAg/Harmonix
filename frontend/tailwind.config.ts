import type { Config } from "tailwindcss";

/**
 * Restrained, government/enterprise palette. One accent (institutional blue),
 * neutral surfaces, and semantic colours reserved for status only -- so a red
 * cell in a table always means "blocked", never "decorative".
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#ffffff",
          subtle: "#f7f8fa",
          muted: "#eef1f5",
          sunken: "#e8ecf1",
        },
        ink: {
          DEFAULT: "#111827",
          muted: "#4b5563",
          subtle: "#6b7280",
          faint: "#9ca3af",
        },
        line: {
          DEFAULT: "#e2e6ec",
          strong: "#cbd2dc",
        },
        accent: {
          50: "#eef4fb",
          100: "#d7e5f6",
          200: "#b0cbec",
          500: "#1d4e89",
          600: "#17406f",
          700: "#123256",
        },
        state: {
          ok: "#1b7f4d",
          okBg: "#e8f5ee",
          warn: "#8a5a00",
          warnBg: "#fdf3e2",
          danger: "#a32020",
          dangerBg: "#fbeaea",
          info: "#1d4e89",
          infoBg: "#eaf1fa",
          neutral: "#4b5563",
          neutralBg: "#f1f3f6",
        },
      },
      fontFamily: {
        sans: [
          "Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI",
          "Roboto", "Helvetica Neue", "Arial", "sans-serif",
        ],
        mono: [
          "ui-monospace", "SFMono-Regular", "Menlo", "Consolas",
          "Liberation Mono", "monospace",
        ],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        xs: ["0.75rem", { lineHeight: "1.125rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.375rem" }],
        lg: ["1rem", { lineHeight: "1.5rem" }],
        xl: ["1.125rem", { lineHeight: "1.625rem" }],
        "2xl": ["1.375rem", { lineHeight: "1.875rem" }],
        "3xl": ["1.75rem", { lineHeight: "2.125rem" }],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(16 24 40 / 0.04)",
        raised: "0 2px 8px -2px rgb(16 24 40 / 0.10), 0 1px 2px 0 rgb(16 24 40 / 0.06)",
      },
      borderRadius: {
        DEFAULT: "4px",
        md: "5px",
        lg: "6px",
      },
    },
  },
  plugins: [],
};

export default config;
