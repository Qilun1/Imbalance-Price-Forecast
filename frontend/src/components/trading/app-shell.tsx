"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Keyboard, Undo2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useMemo, useState } from "react";

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { queries } from "@/lib/api/queries";
import { formatDateTimeUtc } from "@/lib/format";
import { useConnectionEvents } from "@/lib/realtime/connection";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { CompactNav, SCREENS, Sidebar, useScreenHref } from "./sidebar";
import { SHORTCUTS, useShortcuts } from "./use-shortcuts";

function CommandMenu({ open, onOpenChange, onShortcuts }: { open: boolean; onOpenChange: (open: boolean) => void; onShortcuts: () => void }) {
  const router = useRouter();
  const screenHref = useScreenHref();
  const { current, step, canStep, setTime, toLatest } = useViewingTime();
  const { data: history } = useQuery(queries.alertHistory());

  const reviews = useMemo(
    () => (history?.situations ?? []).filter((situation) => situation.alert.severity === "review").map((situation) => situation.first_origin_utc),
    [history],
  );
  const next = current ? reviews.find((origin) => origin > current) : undefined;
  const previous = current ? reviews.findLast((origin) => origin < current) : undefined;

  const run = (action: () => void) => {
    onOpenChange(false);
    action();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Command menu" description="Go to a screen or move the viewing time.">
      <Command>
        <CommandInput placeholder="Type a command…" />
        <CommandList>
        <CommandEmpty>Nothing matches that.</CommandEmpty>
        <CommandGroup heading="Screens">
          {SCREENS.map(({ href, label, icon: Icon }) => (
            <CommandItem key={href} onSelect={() => run(() => router.push(screenHref(href)))}>
              <Icon aria-hidden />
              {label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Viewing time">
          {next ? (
            <CommandItem onSelect={() => run(() => setTime(next))}>
              <ArrowRight aria-hidden />
              Next situation to review, {formatDateTimeUtc(next)}
            </CommandItem>
          ) : null}
          {previous ? (
            <CommandItem onSelect={() => run(() => setTime(previous))}>
              <ArrowLeft aria-hidden />
              Previous situation to review, {formatDateTimeUtc(previous)}
            </CommandItem>
          ) : null}
          <CommandItem disabled={!canStep(-1)} onSelect={() => run(() => step(-1))}>
            <ArrowLeft aria-hidden />
            One hour back
          </CommandItem>
          <CommandItem disabled={!canStep(1)} onSelect={() => run(() => step(1))}>
            <ArrowRight aria-hidden />
            One hour forward
          </CommandItem>
          <CommandItem onSelect={() => run(toLatest)}>
            <Undo2 aria-hidden />
            Back to the latest forecast
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Help">
          <CommandItem onSelect={() => run(onShortcuts)}>
            <Keyboard aria-hidden />
            Keyboard shortcuts
          </CommandItem>
        </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}

function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>They do not fire while you are typing.</DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {SHORTCUTS.map(({ keys, action }) => (
            <div key={keys} className="contents">
              <dt className="font-mono text-xs text-ink">{keys}</dt>
              <dd className="text-stone">{action}</dd>
            </div>
          ))}
        </dl>
        {/* Lightweight Charts' licence asks for this notice and link on the page. */}
        <p className="border-t pt-3 text-xs text-muted-foreground">
          Charts use{" "}
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer" className="underline underline-offset-2">
            TradingView Lightweight Charts™
          </a>
          , copyright TradingView, Inc.
        </p>
      </DialogContent>
    </Dialog>
  );
}

/** Shown whenever the API serves invented data, so a recording or screenshot cannot pass for real prices. */
function DemoDataBanner() {
  const { data: meta } = useQuery(queries.meta());
  if (meta?.mode !== "mock") return null;
  return (
    <p role="status" className="shrink-0 border-b bg-warning-bg px-3 py-1 text-center text-xs text-warning">
      Demo data. {meta.note}
    </p>
  );
}

export function AppShell({ startsAsRail, children }: { startsAsRail: boolean; children: ReactNode }) {
  const [commandOpen, setCommandOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const showShortcuts = () => setShortcutsOpen(true);
  const showCommand = () => setCommandOpen(true);

  useConnectionEvents();
  useShortcuts({ onCommand: showCommand, onShortcuts: showShortcuts });

  return (
    <div className="flex h-dvh overflow-hidden">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-2">
        Skip to the content
      </a>
      <Sidebar startsAsRail={startsAsRail} />
      <div className="flex min-w-0 flex-1 flex-col">
        <DemoDataBanner />
        {/* Phones only: the sidebar is hidden there, so the screens are listed here. */}
        <header className="flex shrink-0 items-center border-b bg-canvas px-3 py-2 md:hidden">
          <CompactNav />
        </header>
        <main id="main" className="scrollbar-thin flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-3">
          {children}
        </main>
      </div>
      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} onShortcuts={showShortcuts} />
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}
