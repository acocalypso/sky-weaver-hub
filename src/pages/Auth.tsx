import { useState, useEffect } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Telescope, Loader2 } from "lucide-react";
import { Starfield } from "@/components/Starfield";
import { toast } from "sonner";
import { z } from "zod";

const schema = z.object({
  email: z.string().trim().email("Invalid email").max(255),
  password: z.string().min(6, "Min 6 characters").max(128),
});

export default function AuthPage() {
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => { document.title = "Sign in · AllSky Control Hub"; }, []);

  if (loading) return null;
  if (user) return <Navigate to="/" replace />;

  const handle = async (mode: "signin" | "signup") => {
    const parsed = schema.safeParse({ email, password });
    if (!parsed.success) { toast.error(parsed.error.issues[0].message); return; }
    setBusy(true);
    try {
      if (mode === "signup") {
        const { error } = await supabase.auth.signUp({
          email, password,
          options: { emailRedirectTo: window.location.origin },
        });
        if (error) throw error;
        toast.success("Account created — signing you in…");
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
      navigate("/");
    } catch (e: any) {
      toast.error(e.message ?? "Authentication failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4">
      <Starfield />
      <div className="relative z-10 w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex h-14 w-14 rounded-xl bg-gradient-primary items-center justify-center glow-primary mb-4">
            <Telescope className="h-7 w-7 text-primary-foreground" />
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">AllSky Control Hub</h1>
          <p className="text-sm text-muted-foreground mt-2">Observatory-grade control for your all-sky camera</p>
        </div>

        <Card className="p-6 telemetry-card">
          <Tabs defaultValue="signin">
            <TabsList className="grid grid-cols-2 mb-6">
              <TabsTrigger value="signin">Sign in</TabsTrigger>
              <TabsTrigger value="signup">Create account</TabsTrigger>
            </TabsList>

            {(["signin", "signup"] as const).map((mode) => (
              <TabsContent key={mode} value={mode} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor={`email-${mode}`}>Email</Label>
                  <Input id={`email-${mode}`} type="email" autoComplete="email"
                    value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`pw-${mode}`}>Password</Label>
                  <Input id={`pw-${mode}`} type="password"
                    autoComplete={mode === "signin" ? "current-password" : "new-password"}
                    value={password} onChange={(e) => setPassword(e.target.value)} />
                </div>
                <Button className="w-full" disabled={busy} onClick={() => handle(mode)}>
                  {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  {mode === "signin" ? "Sign in" : "Create account"}
                </Button>
                {mode === "signup" && (
                  <p className="text-xs text-muted-foreground text-center">
                    The first account becomes an <span className="text-primary">admin</span>.
                  </p>
                )}
              </TabsContent>
            ))}
          </Tabs>
        </Card>

        <p className="text-center text-xs text-muted-foreground mt-6">
          API-first · Linux & Raspberry Pi ready
        </p>
      </div>
    </div>
  );
}
