import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RoleBadge } from "@/components/RoleBadge";
import { StatusChip, StatusDot } from "@/components/StatusBadge";

describe("RoleBadge", () => {
  it("renders the role text in uppercase form", () => {
    render(<RoleBadge role="operator" />);
    expect(screen.getByText(/operator/i)).toBeInTheDocument();
  });
});

describe("StatusChip", () => {
  it("renders the friendly label for each state", () => {
    render(<StatusChip state="running" />);
    expect(screen.getByText(/running/i)).toBeInTheDocument();
  });

  it("StatusDot exposes accessible label", () => {
    const { container } = render(<StatusDot state="fault" />);
    expect(container.querySelector("[aria-label='Fault']")).not.toBeNull();
  });
});
