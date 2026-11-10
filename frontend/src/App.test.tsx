import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { NAV } from "./App";
import { Login } from "./screens/Login";
import { ActionBadge, DataBadge, StageBadge } from "./components/ui";

describe("MARKET SAGE PWA", () => {
  it("has exactly the five primary screens", () => {
    expect(NAV.map((n) => n.label)).toEqual(["Home", "Invest", "My Trades", "Analyst", "Performance"]);
  });
  it("labels status with text, not colour alone", () => {
    render(<><ActionBadge action="BUY" /><DataBadge status="synthetic" /><StageBadge stage="early_warning" /></>);
    expect(screen.getByText(/BUY/)).toBeTruthy();
    expect(screen.getByText(/SYNTHETIC/)).toBeTruthy();
    expect(screen.getByText(/not confirmed/)).toBeTruthy();
  });
  it("renders the login screen with advisory notice", () => {
    render(<Login onLogin={() => {}} />);
    expect(screen.getByText(/paper trading only/)).toBeTruthy();
  });
});
