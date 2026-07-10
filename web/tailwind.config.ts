import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        background: "rgb(var(--color-background) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        border: "rgb(var(--color-border) / <alpha-value>)",
        text: "rgb(var(--color-text) / <alpha-value>)",
        subdued: "rgb(var(--color-subdued) / <alpha-value>)",
        faint: "rgb(var(--color-faint) / <alpha-value>)",
        silver: "rgb(var(--color-silver) / <alpha-value>)",
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        success: "rgb(var(--color-success) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
        onaccent: "rgb(var(--color-onaccent) / <alpha-value>)"
      },
      fontFamily: {
        sans: ["var(--font-ui)", "Space Grotesk", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "IBM Plex Mono", "ui-monospace", "monospace"]
      },
      backgroundImage: {
        "gold-gradient": "linear-gradient(135deg, #E8C46B, #C9A24B)",
        "gold-mark": "linear-gradient(135deg, #E8C46B, #9A7B2F)",
        "gold-bar": "linear-gradient(90deg, #9A7B2F, #E8C46B)",
        "silver-bar": "linear-gradient(90deg, #7C8087, #C9CDD3)",
        "silver-mark": "linear-gradient(135deg, #C9CDD3, #7C8087)"
      },
      boxShadow: {
        panel: "0 12px 32px rgb(0 0 0 / 0.22)",
        gold: "0 8px 24px rgb(232 196 107 / 0.30)"
      }
    }
  },
  plugins: []
};

export default config;
