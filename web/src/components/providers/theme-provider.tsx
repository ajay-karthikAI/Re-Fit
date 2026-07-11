"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Theme = "dark" | "light";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
};

const STORAGE_KEY = "refit.theme";
const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Site-wide light/dark toggle for the authenticated workspace. Design-token
 * overrides live under `.theme-scope[data-theme="light"]` in globals.css, not
 * `:root` — so the landing hero and login page, which render outside any
 * `.theme-scope` element, always keep the dark Aurum palette regardless of
 * this setting. `document.documentElement.dataset.theme` is set purely for
 * native form-control/scrollbar theming (`html[data-theme="light"]`), which
 * is harmless to apply globally.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") {
      setThemeState(stored);
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setTheme = (next: Theme) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  };

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme,
      toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark")
    }),
    [theme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}

/** Non-throwing variant for components (like ToastProvider) that render fine
 * standalone in unit tests without the full provider tree — falls back to
 * the app's default theme rather than forcing every such test to know about
 * theming. */
export function useOptionalTheme(): Theme {
  const context = useContext(ThemeContext);
  return context?.theme ?? "dark";
}
