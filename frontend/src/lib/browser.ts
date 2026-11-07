"use client";

import { useSyncExternalStore } from "react";

function useMedia(query: string): boolean | null {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => null,
  );
}

/** Both are null until mounted, so the server and the first client render match. */
export const useIsWide = () => useMedia("(min-width: 1280px)");
export const useIsNarrow = () => useMedia("(max-width: 1023px)");

/** Per-viewer conveniences only. Storage can be missing or blocked, and the page must still work. */
export const safeStorage = {
  getItem(key: string): string | null {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // The setting simply will not be remembered.
    }
  },
};
