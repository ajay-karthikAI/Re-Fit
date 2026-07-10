"use client";

import { useTheme } from "@/components/providers/theme-provider";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === "light";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
      aria-pressed={isLight}
      className="relative flex h-8 w-14 shrink-0 items-center rounded-full border border-silver/[0.18] bg-muted px-1 transition-colors"
    >
      <span
        className={[
          "flex h-6 w-6 items-center justify-center rounded-full bg-gold-gradient text-onaccent transition-transform duration-200 ease-out",
          isLight ? "translate-x-6" : "translate-x-0"
        ].join(" ")}
      >
        {isLight ? (
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden>
            <circle cx="7" cy="7" r="3" stroke="currentColor" strokeWidth="1.4" />
            <path
              d="M7 0.8v1.6M7 11.6v1.6M13.2 7h-1.6M2.4 7H0.8M11.3 2.7l-1.1 1.1M3.8 10.2l-1.1 1.1M11.3 11.3l-1.1-1.1M3.8 3.8 2.7 2.7"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        ) : (
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden>
            <path d="M12.2 8.5A5.5 5.5 0 0 1 5.5 1.8a5.5 5.5 0 1 0 6.7 6.7Z" fill="currentColor" />
          </svg>
        )}
      </span>
    </button>
  );
}
