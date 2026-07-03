import type { ReactNode } from "react";
import { Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export function ConfigHelp({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground"
          aria-label={`About ${label}`}
        >
          <Info className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 max-w-[calc(100vw-2rem)] text-sm leading-6">
        <p className="font-medium text-foreground">{label}</p>
        <div className="mt-2 text-muted-foreground">{children}</div>
      </PopoverContent>
    </Popover>
  );
}

export function ConfigLabel({ label, help, htmlFor, className }: { label: string; help?: ReactNode; htmlFor?: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {help && <ConfigHelp label={label}>{help}</ConfigHelp>}
    </div>
  );
}
