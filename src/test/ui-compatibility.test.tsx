import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Calendar } from "@/components/ui/calendar";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { ChartContainer, ChartLegendContent, ChartTooltipContent } from "@/components/ui/chart";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return { ...actual, ResponsiveContainer: ({ children }: { children: React.ReactNode }) => children };
});

describe("UI adapters for installed component APIs", () => {
  it("supports calendar day selection and month navigation", () => {
    const select = vi.fn();
    render(<Calendar mode="single" defaultMonth={new Date(2026, 9, 1)} onSelect={select} />);
    fireEvent.click(screen.getByRole("button", { name: /October 16/ }));
    expect(select.mock.calls[0][0]).toEqual(new Date(2026, 9, 16));
    fireEvent.click(screen.getByRole("button", { name: /next month/i }));
    expect(screen.getByText("November 2026")).toBeInTheDocument();
  });

  it.each(["horizontal", "vertical"] as const)("renders %s panels with an accessible separator", (direction) => {
    render(
      <ResizablePanelGroup direction={direction}>
        <ResizablePanel id="first">First panel</ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="second">Second panel</ResizablePanel>
      </ResizablePanelGroup>,
    );
    expect(screen.getByText("First panel")).toBeInTheDocument();
    expect(screen.getByText("Second panel")).toBeInTheDocument();
    expect(screen.getByRole("separator")).toHaveAttribute("aria-orientation", direction === "horizontal" ? "vertical" : "horizontal");
  });

  it("renders zero tooltip values when raw payload data is absent", () => {
    render(
      <ChartContainer config={{ count: { label: "Captures", color: "#ffffff" } }}>
        <ChartTooltipContent active payload={[{ graphicalItemId: "count", name: "count", value: 0, dataKey: (value) => value.count, color: "#ffffff" }]} />
      </ChartContainer>,
    );
    expect(screen.getByText("Captures")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("passes all tooltip entries to a custom formatter", () => {
    const payload = [{ graphicalItemId: "count", name: "count", value: 3, dataKey: "count", payload: { count: 3 } }];
    const formatter = vi.fn((..._args: unknown[]) => "Formatted count");
    render(<ChartContainer config={{ count: { label: "Captures" } }}><ChartTooltipContent active payload={payload} formatter={formatter} /></ChartContainer>);
    expect(screen.getByText("Formatted count")).toBeInTheDocument();
    expect(formatter.mock.calls[0][4]).toBe(payload);
  });

  it("renders legend payloads using configured labels", () => {
    render(<ChartContainer config={{ count: { label: "Captures" } }}><ChartLegendContent payload={[{ value: "count", dataKey: "count", color: "#ffffff" }]} /></ChartContainer>);
    expect(screen.getByText("Captures")).toBeInTheDocument();
  });
});
