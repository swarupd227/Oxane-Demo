const usd = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatUsd(amount: number): string {
  return `${amount < 0 ? "-" : ""}US$${usd.format(Math.abs(amount))}`;
}

export function formatUsdShort(amount: number): string {
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (abs >= 1_000_000) {
    return `${sign}US$${trimZero(abs / 1_000_000)}m`;
  }
  if (abs >= 1_000) {
    return `${sign}US$${trimZero(abs / 1_000)}k`;
  }
  return formatUsd(amount);
}

function trimZero(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}

const longDate = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function formatDate(isoDate: string): string {
  return longDate.format(new Date(`${isoDate}T00:00:00Z`));
}

export function formatCount(count: number): string {
  return usd.format(count);
}
