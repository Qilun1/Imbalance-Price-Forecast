import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { formatPrice, PRICE_UNIT } from "@/lib/format";
import { type Direction, directionLabel } from "@/lib/forecast";
import { cn } from "@/lib/utils";

/**
 * A background flash when a value changes while being watched (Replay), fading in about 400 ms. The
 * number itself changes instantly. With reduced motion, a static arrow replaces the flash.
 */
function useChange(value: number | null | undefined): "up" | "down" | null {
  const previous = useRef(value);
  const [change, setChange] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    const before = previous.current;
    previous.current = value;
    if (typeof before !== "number" || typeof value !== "number" || before === value) return;
    setChange(value > before ? "up" : "down");
    const timer = setTimeout(() => setChange(null), 400);
    return () => clearTimeout(timer);
  }, [value]);
  return change;
}

export function PriceCell({ value, live = false, className }: { value: number | null | undefined; live?: boolean; className?: string }) {
  const change = useChange(live ? value : null);
  const Arrow = change === "up" ? ArrowUp : ArrowDown;
  return (
    <span className={cn("inline-flex items-center gap-0.5 rounded-xs", change === "up" && "flash-up", change === "down" && "flash-down", className)}>
      {change ? <Arrow className="hidden size-3 motion-reduce:inline" aria-hidden /> : null}
      {formatPrice(value)}
    </span>
  );
}

const DIRECTION_ICON = { up: ArrowUp, down: ArrowDown, none: Minus };
const DIRECTION_TONE = { up: "text-up", down: "text-down", none: "text-muted-foreground" };

/** Direction always pairs its colour with an arrow and a word. */
export function DirectionLabel({ direction, className }: { direction: Direction; className?: string }) {
  const Icon = DIRECTION_ICON[direction];
  return (
    <span className={cn("inline-flex items-center gap-1", DIRECTION_TONE[direction], className)}>
      <Icon className="size-4" aria-hidden />
      {directionLabel(direction)}
    </span>
  );
}

export function Unit() {
  return <span className="text-xs text-muted-foreground">{PRICE_UNIT}</span>;
}
