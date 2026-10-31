import { describe, expect, it } from "vitest";
import { formatDate, formatUsd, formatUsdShort } from "./format";

describe("formatUsd", () => {
  it("shows full precision", () => {
    expect(formatUsd(250_000_000)).toBe("US$250,000,000");
  });

  it("puts the sign before the currency", () => {
    expect(formatUsd(-1_100_000)).toBe("-US$1,100,000");
  });
});

describe("formatUsdShort", () => {
  it("drops a trailing zero", () => {
    expect(formatUsdShort(250_000_000)).toBe("US$250m");
  });

  it("keeps one decimal place", () => {
    expect(formatUsdShort(1_100_000)).toBe("US$1.1m");
  });

  it("uses thousands below a million", () => {
    expect(formatUsdShort(75_000)).toBe("US$75k");
  });
});

describe("formatDate", () => {
  it("does not shift with the viewer's time zone", () => {
    expect(formatDate("2026-03-01")).toBe("1 Mar 2026");
  });
});
