import { describe, it, expect } from "vitest";
import { fmtKw, fmtKwh, fmtNumber, uiStateLabel } from "@/lib/format";

describe("format helpers", () => {
  it("formats numbers with default 1 digit", () => {
    expect(fmtNumber(12.345)).toMatch(/12\.3/);
    expect(fmtNumber(undefined)).toBe("—");
  });

  it("formats kW and kWh with units", () => {
    expect(fmtKw(150)).toMatch(/kW$/);
    expect(fmtKwh(2400)).toMatch(/kWh$/);
  });

  it("maps each ui state to a label", () => {
    expect(uiStateLabel("running")).toBe("Running");
    expect(uiStateLabel("warning")).toBe("Warning");
    expect(uiStateLabel("fault")).toBe("Fault");
    expect(uiStateLabel("offline")).toBe("Offline");
  });
});
