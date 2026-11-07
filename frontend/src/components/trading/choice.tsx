"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

/**
 * A row of pill buttons where exactly one is chosen, read as radio buttons by screen readers.
 * `fill` stretches the buttons evenly across the space their parent gives them.
 */
export function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
  fill = false,
}: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
  fill?: boolean;
}) {
  return (
    <ToggleGroup
      type="single"
      size={fill ? "default" : "sm"}
      spacing={1}
      value={value}
      aria-label={label}
      className={cn(fill && "w-auto min-w-0 flex-1")}
      onValueChange={(next) => {
        if (next) onChange(next as T);
      }}
    >
      {options.map((option) => (
        <ToggleGroupItem key={option.value} value={option.value} className={cn("px-3", fill && "min-w-0 flex-1")}>
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
