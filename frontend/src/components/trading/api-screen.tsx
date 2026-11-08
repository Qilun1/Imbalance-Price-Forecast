"use client";

import { Check, Copy, ExternalLink } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ENDPOINTS, pullExample } from "@/lib/api-guide";

import { PageHeader } from "./page-header";
import { Panel, PanelBody, PanelHeader } from "./panel";

const COPIED_MS = 1500;

/** A path or parameter inside running text. */
function Mono({ children }: { children: ReactNode }) {
  return <code className="rounded-xs bg-fill px-1 py-px font-mono text-xs text-ink">{children}</code>;
}

function copyFailed() {
  toast.error("Could not copy", { description: "Select the text and press Ctrl+C." });
}

/** Copies exactly `text`, the code as written. */
function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(timer);
  }, [copied]);
  const copy = () => {
    // The clipboard needs a secure page: localhost is one, a plain-http address elsewhere is not.
    const clipboard: Clipboard | undefined = navigator.clipboard;
    if (!clipboard) return copyFailed();
    clipboard.writeText(text).then(() => setCopied(true), copyFailed);
  };
  const Icon = copied ? Check : Copy;
  return (
    <>
      <Button variant="ghost" size="sm" aria-label={label} onClick={copy}>
        <Icon aria-hidden />
        {copied ? "Copied" : "Copy"}
      </Button>
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </>
  );
}

/**
 * The brief's Level 2 "plus an API from which this information can be retrieved for display", essentials
 * only: how to pull from the API once it runs in real mode. The interactive docs hold the rest.
 */
export function ApiScreen({ origin }: { origin: string }) {
  const example = pullExample(origin);
  return (
    <div className="mx-auto mt-8 flex w-full max-w-4xl shrink-0 flex-col gap-3">
      <PageHeader title="API">
        <Button variant="outline" size="sm" asChild>
          <a href={`${origin}/docs`} target="_blank" rel="noreferrer">
            Interactive docs
            <ExternalLink aria-hidden />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </Button>
      </PageHeader>
      <p className="text-base text-stone">
        With the model&apos;s forecasts loaded and the API running in real mode, your own tools can pull the same data as this dashboard.
      </p>

      <Panel label="Pull the data">
        <PanelHeader title="Pull the data" highlight />
        <PanelBody className="flex flex-col gap-3">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-px pl-0">Endpoint</TableHead>
                <TableHead>Returns</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ENDPOINTS.map(({ path, returns }) => (
                <TableRow key={path} className="hover:bg-transparent">
                  <TableCell className="pl-0 font-mono text-xs text-ink">{path}</TableCell>
                  <TableCell className="py-1.5 whitespace-normal text-sm text-stone">{returns}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">PowerShell</span>
              <CopyButton text={example} label="Copy the PowerShell example" />
            </div>
            <pre tabIndex={0} className="scrollbar-thin overflow-x-auto rounded-md bg-fill p-3 font-mono text-xs leading-relaxed text-ink">
              <code>{example}</code>
            </pre>
          </div>
          <p className="text-sm text-stone">
            Add <Mono>?as_of=2026-10-23T09:00:00Z</Mono> to see what was known at a past moment. Times are UTC.
          </p>
          <p className="text-sm text-stone">
            On real data <Mono>/forecast</Mono>, <Mono>/actuals</Mono> and <Mono>/hindsight</Mono> include the licensed Nord Pool spot price: keep the API
            on this machine, and never save, log or share that price.
          </p>
        </PanelBody>
      </Panel>
    </div>
  );
}
