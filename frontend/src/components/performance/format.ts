import { intlLocale, type Locale } from "@/lib/i18n";

/** "84 ms", "1,2 s". */
export function formatMs(ms: number | null | undefined, locale: Locale): string {
  if (ms === null || ms === undefined) return "—";
  const nf = (digits: number) =>
    new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  if (ms < 10) return `${nf(1).format(ms)} ms`;
  if (ms < 1000) return `${nf(0).format(ms)} ms`;
  return `${nf(ms < 10_000 ? 2 : 1).format(ms / 1000)} s`;
}

export function formatCount(n: number | null | undefined, locale: Locale, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: digits }).format(n);
}

export function formatBytes(bytes: number | null | undefined, locale: Locale): string {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${formatCount(value, locale, unit ? 1 : 0)} ${units[unit]}`;
}
