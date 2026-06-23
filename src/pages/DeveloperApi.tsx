import { Code2, ExternalLink } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const examples = {
  curl: `curl -H "Authorization: Bearer $SKYWEAVER_API_KEY" \\
  http://skyweaver.local:8765/api/v1/status`,
  javascript: `const res = await fetch("http://skyweaver.local:8765/api/v1/images/latest", {
  headers: { Authorization: \`Bearer \${apiKey}\` },
});
const { data } = await res.json();`,
  python: `import requests

res = requests.get(
    "http://skyweaver.local:8765/api/v1/status",
    headers={"Authorization": f"Bearer {api_key}"},
)
print(res.json()["data"])`,
};

const endpoints = [
  ["Health", "GET", "/api/v1/health", "No auth health probe."],
  ["Status", "GET", "/api/v1/status", "Capture state, active camera, latest image."],
  ["Latest image", "GET", "/api/v1/images/latest", "Mobile-friendly latest image metadata."],
  ["Gallery", "GET", "/api/v1/images?limit=50&offset=0", "Paginated image list."],
  ["Start capture", "POST", "/api/v1/capture/start", "Requires write:capture."],
  ["Stop capture", "POST", "/api/v1/capture/stop", "Requires write:capture."],
  ["Events", "GET", "/api/v1/events/stream", "Server-Sent Events stream."],
];

export default function DeveloperApi() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Developer</p>
          <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
            <Code2 className="h-7 w-7 text-primary" /> Developer API
          </h1>
        </div>
        <Button asChild variant="outline">
          <a href="/api/docs" target="_blank" rel="noreferrer">OpenAPI docs <ExternalLink className="h-4 w-4 ml-2" /></a>
        </Button>
      </div>

      <Card className="telemetry-card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Response format</h2>
        <pre className="rounded-md bg-muted/40 p-3 text-xs font-mono-data overflow-auto">{`{
  "data": { ... },
  "meta": {
    "request_id": "...",
    "timestamp": "..."
  }
}`}</pre>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {Object.entries(examples).map(([name, code]) => (
          <Card key={name} className="telemetry-card space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{name}</h2>
            <pre className="rounded-md bg-muted/40 p-3 text-xs font-mono-data overflow-auto min-h-32">{code}</pre>
          </Card>
        ))}
      </div>

      <Card className="telemetry-card space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Core endpoints</h2>
        <div className="divide-y divide-border/60">
          {endpoints.map(([name, method, path, description]) => (
            <div key={path} className="grid grid-cols-1 gap-2 py-3 md:grid-cols-[140px_80px_1fr_1.5fr] md:items-center">
              <span className="font-medium">{name}</span>
              <span className="font-mono-data text-primary">{method}</span>
              <span className="font-mono-data text-sm">{path}</span>
              <span className="text-sm text-muted-foreground">{description}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
