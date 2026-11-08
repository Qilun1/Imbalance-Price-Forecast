"use client";

import { useRouter } from "next/navigation";
import { useEffect, useEffectEvent } from "react";

import { useViewingTime } from "@/lib/realtime/viewing-time";

import { SCREENS, useScreenHref } from "./sidebar";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** F6 moves focus from panel to panel, in reading order. */
function focusNextPanel(direction: 1 | -1): void {
  const panels = [...document.querySelectorAll<HTMLElement>("[data-panel]")];
  if (!panels.length) return;
  const current = panels.findIndex((panel) => panel.contains(document.activeElement));
  panels.at((current + direction) % panels.length)?.focus();
}

/**
 * Keys are chosen to work on a Finnish keyboard, where [ and ] need AltGr. Nothing fires while typing,
 * or when a focused control has used the key itself, such as the chart or a menu.
 */
export function useShortcuts({ onCommand, onShortcuts }: { onCommand: () => void; onShortcuts: () => void }) {
  const router = useRouter();
  const screenHref = useScreenHref();
  const { step, canStep, toLatest, toggleReplay, isPast } = useViewingTime();

  const onKeyDown = useEffectEvent((event: KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      onCommand();
      return;
    }
    if (event.key === "F6") {
      event.preventDefault();
      focusNextPanel(event.shiftKey ? -1 : 1);
      return;
    }
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
    if (document.querySelector("[role=dialog]")) return;

    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const hours = (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 24 : 1);
      if (canStep(hours)) {
        event.preventDefault();
        step(hours);
      }
      return;
    }
    if (event.key === "?") onShortcuts();
    if (event.key.toLowerCase() === "l") toLatest();
    if (event.key.toLowerCase() === "r" && isPast) toggleReplay();
    const screen = SCREENS[Number(event.key) - 1];
    if (screen) router.push(screenHref(screen.href));
  });

  useEffect(() => {
    const listener = (event: KeyboardEvent) => onKeyDown(event);
    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, []);
}

export const SHORTCUTS: readonly { keys: string; action: string }[] = [
  { keys: "← →", action: "One hour back or forward" },
  { keys: "Shift + ← →", action: "One day back or forward" },
  { keys: "L", action: "Back to the latest forecast" },
  { keys: "R", action: "Replay a past moment hour by hour, or pause" },
  { keys: "1 2 3 4 5", action: "Now, Next 10 h, Hindsight, CHP, API" },
  { keys: "F6", action: "Move between panels" },
  { keys: "Ctrl + K", action: "Command menu" },
  { keys: "?", action: "This list" },
];
