/*
 * Fails the build if a colour pair in src/styles/tokens.css drops below WCAG AA:
 * 4.5:1 for text, 3:1 for UI and chart marks. Runs before every build (`npm run contrast`).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const css = readFileSync(join(root, "src/styles/tokens.css"), "utf8");
const tokens = Object.fromEntries([...css.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-f]{6});/g)].map((m) => [m[1], m[2]]));

const TEXT = 4.5;
const UI = 3;
const LIGHT = ["canvas", "surface", "fill"];

const pairs = [
  ...["ink", "stone", "text-muted", "clay", "up", "down", "warning", "info", "error-text"].flatMap((text) =>
    LIGHT.map((background) => [text, background, TEXT]),
  ),
  ["up", "up-bg", TEXT],
  ["down", "down-bg", TEXT],
  ["warning", "warning-bg", TEXT],
  ["info", "info-bg", TEXT],
  ["error-text", "error-bg", TEXT],
  ["ink", "up-bg", TEXT],
  ["ink", "down-bg", TEXT],
  ["on-action", "action", TEXT],
  ["on-action", "action-hover", TEXT],
  ["on-stone", "stone", TEXT],
  ["on-stone", "stone-hover", TEXT],
  ["on-dark", "ink-band-soft", TEXT],
  ["on-dark", "sidebar-hover", TEXT],
  ["mute", "ink-band-soft", TEXT],
  ["canvas", "ink-band-soft", TEXT],
  ["stone", "canvas", TEXT],
  ["control-border", "surface", UI],
  ["control-border", "canvas", UI],
  ["focus", "canvas", UI],
  ["focus", "surface", UI],
  ["focus-on-dark", "ink-band-soft", UI],
  ["chart-axis", "surface", TEXT],
  ["chart-crosshair", "surface", UI],
  ...[1, 2, 3, 4, 5, 6].flatMap((slot) => [[`series-${slot}`, "surface", UI], [`series-${slot}`, "canvas", UI]]),
];

function luminance(hex) {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

const failures = [];
for (const [foreground, background, minimum] of pairs) {
  const [fg, bg] = [tokens[foreground], tokens[background]];
  if (!fg || !bg) {
    failures.push(`${foreground} on ${background}: token missing`);
    continue;
  }
  const value = ratio(fg, bg);
  if (value < minimum) failures.push(`${foreground} on ${background}: ${value.toFixed(2)} (needs ${minimum})`);
}

if (failures.length) {
  console.error(`Contrast check failed:\n  ${failures.join("\n  ")}`);
  process.exit(1);
}
console.log(`Contrast check passed: ${pairs.length} pairs, ${Object.keys(tokens).length} colour tokens.`);
