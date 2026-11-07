"use client";

import { ArrowUp, CircleAlert, Plus, Search } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { DirectionLabel } from "@/components/trading/cells";
import { KpiCard, KpiCardSkeleton } from "@/components/trading/kpi-card";
import { Panel, PanelBody, PanelError, PanelHeader, PanelMessage, SkeletonLines } from "@/components/trading/panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { NOT_ANSWERING } from "@/lib/api/errors";

const SWATCHES = [
  "bg-action",
  "bg-stone",
  "bg-ink",
  "bg-up",
  "bg-down",
  "bg-warning",
  "bg-info",
  "bg-error-text",
  "bg-series-1",
  "bg-series-2",
  "bg-series-3",
  "bg-series-4",
  "bg-series-5",
  "bg-series-6",
  "bg-chart-band",
];

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border bg-card p-4">
      <h2 className="eyebrow text-stone">{title}</h2>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  );
}

/** Hidden page: every primitive in every state, so restyling can be checked at a glance. */
export default function DevUiPage() {
  return (
    <TooltipProvider>
      <main className="mx-auto flex max-w-6xl flex-col gap-3 p-6">
        <h1 className="font-title text-3xl text-ink">Primitives</h1>

        <Group title="Buttons">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Stone</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="link">Link</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
          <Button variant="outline" size="icon" aria-label="Add">
            <Plus aria-hidden />
          </Button>
          <Button size="sm">Small</Button>
          <Button size="lg">Large</Button>
        </Group>

        <Group title="Inputs">
          <Input className="w-48" placeholder="Default" aria-label="Default" />
          <Input className="w-48" defaultValue="Invalid" aria-invalid aria-label="Invalid" />
          <Input className="w-48" placeholder="Disabled" disabled aria-label="Disabled" />
          <Select>
            <SelectTrigger className="w-48" aria-label="Select">
              <SelectValue placeholder="Select" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="one">One</SelectItem>
              <SelectItem value="two">Two</SelectItem>
            </SelectContent>
          </Select>
          <Switch aria-label="Off" />
          <Switch defaultChecked aria-label="On" />
          <Switch disabled aria-label="Disabled" />
        </Group>

        <Group title="Tabs and toggles">
          <Tabs defaultValue="one">
            <TabsList>
              <TabsTrigger value="one">One</TabsTrigger>
              <TabsTrigger value="two">Two</TabsTrigger>
              <TabsTrigger value="three" disabled>
                Disabled
              </TabsTrigger>
            </TabsList>
            <TabsContent value="one">First tab</TabsContent>
            <TabsContent value="two">Second tab</TabsContent>
          </Tabs>
          <ToggleGroup type="single" defaultValue="week" spacing={1} aria-label="Period">
            <ToggleGroupItem value="day">Day</ToggleGroupItem>
            <ToggleGroupItem value="week">Week</ToggleGroupItem>
            <ToggleGroupItem value="month" disabled>
              Month
            </ToggleGroupItem>
          </ToggleGroup>
        </Group>

        <Group title="Badges and direction">
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="up">
            <ArrowUp aria-hidden />
            Up
          </Badge>
          <Badge variant="down">Down</Badge>
          <Badge variant="error">Review</Badge>
          <Badge variant="warning">Watch</Badge>
          <Badge variant="info">Info</Badge>
          <Badge variant="destructive">Error</Badge>
          <DirectionLabel direction="up" />
          <DirectionLabel direction="down" />
          <DirectionLabel direction="none" />
        </Group>

        <Group title="Overlays">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="outline">Tooltip</Button>
            </TooltipTrigger>
            <TooltipContent>A short hint</TooltipContent>
          </Tooltip>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline">Popover</Button>
            </PopoverTrigger>
            <PopoverContent>
              <Calendar mode="single" />
            </PopoverContent>
          </Popover>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">Menu</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem>First</DropdownMenuItem>
              <DropdownMenuItem>Second</DropdownMenuItem>
              <DropdownMenuItem disabled>Disabled</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline">Dialog</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Dialog title</DialogTitle>
                <DialogDescription>A short description.</DialogDescription>
              </DialogHeader>
            </DialogContent>
          </Dialog>
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline">Sheet</Button>
            </SheetTrigger>
            <SheetContent>
              <SheetHeader>
                <SheetTitle>Sheet title</SheetTitle>
                <SheetDescription>A short description.</SheetDescription>
              </SheetHeader>
            </SheetContent>
          </Sheet>
          <Button variant="outline" onClick={() => toast.success("Copied as a shift note")}>
            Toast
          </Button>
        </Group>

        <Group title="Table">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead className="text-right">P50</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>16:00</TableCell>
                <TableCell className="text-right">63.9</TableCell>
              </TableRow>
              <TableRow data-state="selected">
                <TableCell>16:15</TableCell>
                <TableCell className="text-right">65.1</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Group>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <KpiCard label="Default" value="63.9" detail="With a line of context" />
          <KpiCardSkeleton label="Loading" />
          <Panel label="Empty">
            <PanelHeader title="Empty" />
            <PanelBody>
              <PanelMessage icon={Search} title="Nothing here">
                One line of explanation.
              </PanelMessage>
            </PanelBody>
          </Panel>
          <Panel label="Error">
            <PanelHeader title="Error" />
            <PanelBody>
              <PanelError error={new Error(NOT_ANSWERING)} onRetry={() => undefined} onBackToLatest={() => undefined} />
            </PanelBody>
          </Panel>
        </div>

        <Group title="Loading">
          <Skeleton className="h-8 w-48" />
          <SkeletonLines rows={2} className="w-48" />
          <CircleAlert className="size-5 text-warning" aria-hidden />
        </Group>

        <Group title="Colour tokens">
          {SWATCHES.map((swatch) => (
            <span key={swatch} className={`size-8 rounded-md ${swatch}`} title={swatch} />
          ))}
        </Group>
      </main>
      <Toaster />
    </TooltipProvider>
  );
}
