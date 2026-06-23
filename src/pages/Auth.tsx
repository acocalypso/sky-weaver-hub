import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Starfield } from "@/components/Starfield";
import { useAuth } from "@/hooks/useAuth";
import { Loader2, Telescope } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";

const schema = z.object({
  username: z.string().trim().min(1, "Username is required").max(255),
  password: z.string().min(6, "Min 6 characters").max(128),
});

export default function AuthPage() {
  const navigate = useNavigate();
  const { user, loading, signIn } = useAuth();
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  useEffect(() => { document.title = "Sign in - Sky Weaver Hub"; }, []);

  if (loading) return null;
  if (user) return <Navigate to="/" replace />;

  async function handle() {
    const parsed = schema.safeParse({ username, password });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0].message);
      return;
    }
    setBusy(true);
    try {
      await signIn(username, password);
      navigate("/");
    } catch (e: any) {
      toast.error(e.message ?? "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4">
      <Starfield />
      <div className="relative z-10 w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex h-14 w-14 rounded-xl bg-gradient-primary items-center justify-center glow-primary mb-4">
            <Telescope className="h-7 w-7 text-primary-foreground" />
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Sky Weaver Hub</h1>
          <p className="text-sm text-muted-foreground mt-2">Local-first all-sky camera control for Raspberry Pi</p>
        </div>

        <Card className="p-6 telemetry-card">
          <Tabs defaultValue="signin">
            <TabsList className="grid grid-cols-1 mb-6">
              <TabsTrigger value="signin">Sign in</TabsTrigger>
            </TabsList>
            <TabsContent value="signin" className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <Button className="w-full" disabled={busy} onClick={handle}>
                {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Sign in
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                Bootstrap password defaults to <span className="font-mono">skyweaver-change-me</span> until setup changes it.
              </p>
            </TabsContent>
          </Tabs>
        </Card>

        <p className="text-center text-xs text-muted-foreground mt-6">REST API first - Linux and Raspberry Pi ready</p>
      </div>
    </div>
  );
}
