import { cn } from "@/lib/utils";

type Variant = "ok" | "warn" | "error" | "idle" | "active";

const colors: Record<Variant, string> = {
  ok: "text-status-ok bg-status-ok/10 border-status-ok/30",
  warn: "text-status-warn bg-status-warn/10 border-status-warn/30",
  error: "text-status-error bg-status-error/10 border-status-error/30",
  idle: "text-status-idle bg-status-idle/10 border-status-idle/30",
  active: "text-status-active bg-status-active/10 border-status-active/30",
};

export function StatusBadge({
  variant = "idle", children, pulse = false, className,
}: { variant?: Variant; children: React.ReactNode; pulse?: boolean; className?: string }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-2 px-2.5 py-1 rounded-md border text-xs font-medium font-mono-data uppercase tracking-wider",
      colors[variant], className,
    )}>
      <span className={cn("status-dot", `text-status-${variant}`, pulse && "pulse-glow rounded-full")} />
      {children}
    </span>
  );
}
