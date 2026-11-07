"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowDownToLine, ArrowUpFromLine } from "lucide-react";
import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Alert, Forecast } from "@/lib/api/client";
import { type Exposure, exposure, type Side } from "@/lib/exposure";
import { formatCount, formatMegawatts, formatScore, formatSignedEuro, formatWindow } from "@/lib/format";
import { STEPS_PER_HOUR, stepsInWindow, windowOf } from "@/lib/forecast";

const MAX_MEGAWATTS = 500;

const schema = z.object({
  side: z.enum(["short", "long"]),
  // Finnish keyboards and habits give a decimal comma.
  megawatts: z
    .string()
    .trim()
    .min(1, "Enter a size in MW.")
    .transform((text) => Number(text.replace(",", ".")))
    .pipe(z.number({ error: "Enter a number." }).positive("Enter more than 0 MW.").max(MAX_MEGAWATTS, `Enter at most ${MAX_MEGAWATTS} MW.`)),
  window: z.string().min(1),
});

type FormInput = { side: Side; megawatts: string; window: string };
type FormOutput = z.output<typeof schema>;

type Choice = { value: string; label: string; start: string; end: string };

function choices(forecast: Forecast, alerts: readonly Alert[]): Choice[] {
  const { steps } = forecast;
  const first = steps[0]?.delivery_start_utc;
  const span = (hours: number, label: string): Choice[] => {
    const end = steps[hours * STEPS_PER_HOUR]?.delivery_start_utc ?? steps.at(-1)?.delivery_start_utc;
    return first && end ? [{ value: label, label, start: first, end }] : [];
  };
  const situations = alerts
    .filter((alert) => alert.kind !== "stale_data")
    .map((alert) => {
      const window = windowOf(alert);
      return { value: `${alert.kind}|${window.start}`, label: `${formatWindow(window.start, window.end)}: ${alert.title}`, ...window };
    });
  const unique = new Map([...span(1, "Next hour"), ...span(4, "Next 4 hours"), ...span(10, "Whole 10 hours"), ...situations].map((choice) => [choice.value, choice]));
  return [...unique.values()];
}

function Result({ result, side, megawatts, window }: { result: Exposure; side: Side; megawatts: number; window: string }) {
  const cost = result.expected >= 0;
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-1 rounded-md bg-fill p-3">
      <p className="text-xs text-stone">
        {side === "short" ? "Short" : "Long"} {formatMegawatts(megawatts)} for {window}, {formatScore(result.megawattHours, 1)} MWh
      </p>
      <p className="font-title text-3xl text-ink">{formatSignedEuro(result.expected)}</p>
      <p className="text-sm text-stone">Expected {cost ? "extra cost" : "gain"} compared with spot</p>
      <p className="text-xs text-muted-foreground">
        P10 to P90 range {formatSignedEuro(result.low)} to {formatSignedEuro(result.high)}. The range sums every quarter-hour&apos;s P10 and P90, so the
        real one is narrower.
      </p>
      {result.missingSpot ? <p className="text-xs text-warning">{formatCount(result.missingSpot)} quarter-hours left out: spot not published yet.</p> : null}
    </div>
  );
}

/**
 * Turns EUR/MWh into euros for an open position the expert types in. Open data cannot show the real
 * position, so nothing here is a recommendation.
 */
export function ExposureCheck({ forecast, alerts }: { forecast: Forecast; alerts: readonly Alert[] }) {
  const options = useMemo(() => choices(forecast, alerts), [forecast, alerts]);
  const [outcome, setOutcome] = useState<{ result: Exposure; side: Side; megawatts: number; window: string } | null>(null);
  const form = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(schema),
    defaultValues: { side: "short", megawatts: "", window: "Next hour" },
  });

  const submit = (values: FormOutput) => {
    const choice = options.find((option) => option.value === values.window) ?? options[0];
    if (!choice) return;
    const steps = stepsInWindow(forecast.steps, choice);
    setOutcome({
      result: exposure(steps, values.side, values.megawatts),
      side: values.side,
      megawatts: values.megawatts,
      window: formatWindow(choice.start, choice.end),
    });
  };

  const clear = () => {
    form.reset();
    setOutcome(null);
  };

  return (
    <form
      noValidate
      className="flex flex-col gap-3"
      onSubmit={form.handleSubmit(submit)}
      onKeyDown={(event) => {
        if (event.key === "Escape") clear();
      }}
    >
      <Controller
        control={form.control}
        name="side"
        render={({ field }) => (
          <Field>
            <FieldLabel id="exposure-side">Open position</FieldLabel>
            <ToggleGroup
              type="single"
              size="default"
              spacing={1}
              value={field.value}
              aria-labelledby="exposure-side"
              onValueChange={(value) => {
                if (value) field.onChange(value);
              }}
            >
              <ToggleGroupItem value="short" className="px-3">
                <ArrowDownToLine aria-hidden />
                Short
              </ToggleGroupItem>
              <ToggleGroupItem value="long" className="px-3">
                <ArrowUpFromLine aria-hidden />
                Long
              </ToggleGroupItem>
            </ToggleGroup>
          </Field>
        )}
      />
      <Controller
        control={form.control}
        name="megawatts"
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="exposure-mw">Size, MW</FieldLabel>
            <Input {...field} id="exposure-mw" inputMode="decimal" autoComplete="off" aria-invalid={fieldState.invalid} placeholder="For example 5…" spellCheck={false} />
            {fieldState.error ? <FieldError>{fieldState.error.message}</FieldError> : null}
          </Field>
        )}
      />
      <Controller
        control={form.control}
        name="window"
        render={({ field }) => (
          <Field>
            <FieldLabel id="exposure-window">Period</FieldLabel>
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger aria-labelledby="exposure-window" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {options.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}
      />
      <div className="flex gap-2">
        <Button type="submit" disabled={form.formState.isSubmitting}>
          Estimate
        </Button>
        <Button type="button" variant="ghost" onClick={clear}>
          Clear
        </Button>
      </div>
      {outcome ? <Result {...outcome} /> : <p className="text-sm text-muted-foreground">Enter a position to see what it could cost compared with spot.</p>}
      <p className="text-xs text-muted-foreground">An estimate from the forecast, not a recommendation. We do not know your real position.</p>
    </form>
  );
}
