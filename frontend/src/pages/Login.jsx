import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { formatApiErrorDetail } from "../lib/api";
import { HardHat, Loader2 } from "lucide-react";

const DEMO = [
  { email: "admin@bedforge.com", password: "admin123", label: "Plant Admin" },
  { email: "supervisor@bedforge.com", password: "Super1234!", label: "Supervisor" },
  { email: "tech@bedforge.com", password: "Tech1234!", label: "QC Tech" },
  { email: "production@bedforge.com", password: "Prod1234!", label: "Production" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex grain">
      {/* Left visual */}
      <div className="hidden lg:flex w-1/2 relative border-r border-border overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(41,121,255,0.3),_transparent_38%),linear-gradient(160deg,_rgba(15,23,42,0.92),_rgba(10,12,16,1))]" />
        <div className="absolute -top-20 -left-12 w-72 h-72 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute bottom-12 right-0 w-80 h-80 rounded-full bg-white/5 blur-3xl" />
        <div className="absolute inset-x-10 top-16 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
        <div className="relative z-10 flex flex-col justify-end p-12">
          <div className="text-primary font-mono text-xs tracking-[0.4em] mb-4">PRESTRESS SERVICES INDUSTRIES LLC</div>
          <h2 className="font-display font-extrabold text-5xl uppercase tracking-tight leading-none">
            Paperless<br />QC & Digital<br />Twin Platform
          </h2>
          <p className="text-muted-foreground mt-4 max-w-md">
            8 beds. Every beam. Real-time tolerance gates, tension validation, and 3D anomaly capture — built for the plant floor.
          </p>
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-3 mb-10">
            <div className="w-12 h-12 bg-primary flex items-center justify-center rounded-sm">
              <HardHat className="w-7 h-7 text-white" />
            </div>
            <div>
              <div className="font-display font-extrabold text-2xl tracking-tight leading-none">BEDFORGE QC</div>
              <div className="text-[10px] tracking-[0.3em] text-muted-foreground font-mono">SECURE ACCESS</div>
            </div>
          </div>

          <form onSubmit={submit} className="space-y-5">
            <div className="border border-border rounded-sm px-4 py-3 bg-card/70 text-sm text-muted-foreground">
              Fields start empty for demo safety. Use a seeded demo shortcut below or sign in with your assigned credentials.
            </div>
            <div>
              <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Email</label>
              <input
                data-testid="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-2 w-full min-h-12 bg-card border border-border rounded-sm px-4 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
                required
              />
            </div>
            <div>
              <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Password</label>
              <input
                data-testid="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-2 w-full min-h-12 bg-card border border-border rounded-sm px-4 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
                required
              />
            </div>

            {error && (
              <div data-testid="login-error" className="border border-destructive text-destructive text-sm px-4 py-3 rounded-sm font-mono">
                [ERROR] {error}
              </div>
            )}

            <button
              data-testid="login-submit"
              type="submit"
              disabled={loading}
              className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-sm hover:bg-white hover:text-black transition-colors duration-100 flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {loading && <Loader2 className="w-5 h-5 animate-spin" />}
              {loading ? "Authenticating" : "Sign In"}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-border">
            <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-3">Quick Demo Login</div>
            <div className="grid grid-cols-2 gap-2">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  data-testid={`demo-${d.label.toLowerCase()}`}
                  type="button"
                  onClick={() => { setEmail(d.email); setPassword(d.password); }}
                  className="min-h-12 border border-border rounded-sm text-sm font-semibold hover:border-primary hover:text-primary transition-colors duration-100"
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
