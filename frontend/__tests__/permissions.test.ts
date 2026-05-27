import { describe, it, expect } from "vitest";
import { can } from "@/lib/permissions";

describe("permissions.can", () => {
  it("allows operator to ack but not resolve", () => {
    expect(can("operator", "alarm.ack")).toBe(true);
    expect(can("operator", "alarm.resolve")).toBe(false);
  });

  it("allows engineer to resolve and view audit", () => {
    expect(can("engineer", "alarm.resolve")).toBe(true);
    expect(can("engineer", "audit.view")).toBe(true);
    expect(can("engineer", "report.generate")).toBe(false);
  });

  it("allows manager to generate reports but not manage users", () => {
    expect(can("manager", "report.generate")).toBe(true);
    expect(can("manager", "user.manage")).toBe(false);
  });

  it("allows admin everything", () => {
    expect(can("admin", "user.manage")).toBe(true);
    expect(can("admin", "report.generate")).toBe(true);
  });

  it("denies all when role is null", () => {
    expect(can(null, "view.dashboards")).toBe(false);
  });
});
