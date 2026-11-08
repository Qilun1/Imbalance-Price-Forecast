"use client";

import { Activity, Braces, Factory, History, type LucideIcon, PanelLeftClose, PanelLeftOpen, Table2 } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsNarrow } from "@/lib/browser";
import { cn } from "@/lib/utils";

export const SIDEBAR_COOKIE = "sidebar";

export const SCREENS: readonly { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Now", icon: Activity },
  { href: "/next-10h", label: "Next 10 h", icon: Table2 },
  { href: "/hindsight", label: "Hindsight", icon: History },
  { href: "/operator", label: "Naantali CHP", icon: Factory },
  { href: "/api-guide", label: "API", icon: Braces },
];

const SPRING = { type: "spring", stiffness: 500, damping: 40 } as const;

function saveWidth(rail: boolean) {
  document.cookie = `${SIDEBAR_COOKIE}=${rail ? "rail" : "wide"}; path=/; max-age=31536000; samesite=lax`;
}

/**
 * Keeps the viewing time when moving between screens. In the browser the query is read from the address
 * when the link is built, not from the last render: a shortcut pressed right after the time changed must
 * carry the new time. useSearchParams still re-renders the links whenever the address changes.
 */
export function useScreenHref() {
  const searchParams = useSearchParams();
  const rendered = searchParams.toString();
  return (href: string) => {
    // Re-encoded like useSearchParams, so the first render in the browser matches the server's HTML.
    const query = typeof window === "undefined" ? rendered : new URLSearchParams(window.location.search).toString();
    return query ? `${href}?${query}` : href;
  };
}

function NavItem({ href, label, icon: Icon, rail, active }: { href: string; label: string; icon: LucideIcon; rail: boolean; active: boolean }) {
  const screenHref = useScreenHref();
  const link = (
    <Link
      href={screenHref(href)}
      aria-current={active ? "page" : undefined}
      aria-label={rail ? label : undefined}
      className={cn(
        "relative flex h-9 items-center gap-2.5 rounded-full px-3 text-base transition-[color,background-color] duration-150 ease-out",
        rail && "w-9 justify-center px-0",
        active ? "font-medium text-stone" : "text-on-dark hover:bg-sidebar-hover",
      )}
    >
      {active ? <motion.span layoutId="active-screen" className="absolute inset-0 rounded-full bg-canvas" transition={SPRING} /> : null}
      <Icon className="relative size-5 shrink-0" aria-hidden />
      {rail ? null : <span className="relative">{label}</span>}
    </Link>
  );
  if (!rail) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

export function Sidebar({ startsAsRail }: { startsAsRail: boolean }) {
  const pathname = usePathname();
  const [saved, setSaved] = useState(startsAsRail);
  const narrow = useIsNarrow();
  const rail = saved || narrow === true;
  const toggle = () => {
    saveWidth(!saved);
    setSaved(!saved);
  };
  const Toggle = rail ? PanelLeftOpen : PanelLeftClose;
  return (
    <aside className={cn("on-dark hidden shrink-0 flex-col bg-ink-band-soft text-on-dark md:flex", rail ? "w-sidebar-rail items-center" : "w-sidebar")}>
      <div className={cn("flex h-topbar shrink-0 items-center", rail ? "justify-center" : "px-4")}>
        <span className="text-base font-semibold text-on-dark">{rail ? "IF" : "Imbalance forecast"}</span>
      </div>
      <nav aria-label="Screens" className={cn("flex flex-1 flex-col gap-1", rail ? "items-center" : "px-3")}>
        {SCREENS.map((screen) => (
          <NavItem key={screen.href} {...screen} rail={rail} active={pathname === screen.href} />
        ))}
      </nav>
      <div className={cn("flex p-3", rail ? "justify-center" : "justify-end", narrow && "hidden")}>
        <Button
          variant="ghost"
          size="icon"
          className="text-on-dark hover:bg-sidebar-hover"
          aria-label={rail ? "Expand the sidebar" : "Collapse the sidebar"}
          onClick={toggle}
        >
          <Toggle className="size-5" aria-hidden />
        </Button>
      </div>
    </aside>
  );
}

/** Below the sidebar's breakpoint the screens move into the top bar. */
export function CompactNav() {
  const pathname = usePathname();
  const screenHref = useScreenHref();
  return (
    <nav aria-label="Screens" className="flex gap-1 md:hidden">
      {SCREENS.map(({ href, label }) => (
        <Link
          key={href}
          href={screenHref(href)}
          aria-current={pathname === href ? "page" : undefined}
          className={cn("flex h-11 items-center rounded-full px-3 text-sm", pathname === href ? "bg-stone text-on-stone" : "text-stone")}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
