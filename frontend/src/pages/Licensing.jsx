import React, { useEffect, useState } from "react";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { toast } from "sonner";

export default function Licensing() {
  const [license, setLicense] = useState(null);
  const [form, setForm] = useState({ license_key: "BF-ENT-2026-DEMO", tier: "enterprise", expires_at: "2027-12-31" });

  const load = () => api.get("/license").then((res) => setLicense(res.data));
  useEffect(() => { load(); }, []);

  const activate = async () => {
    try {
      await api.post("/license/activate", form);
      await load();
      toast.success("License activated");
    } catch {
      toast.error("Activation failed");
    }
  };

  return (
    <Layout>
      <PageHeader title="Licensing" subtitle="Trial, activation, feature flags by tier, and graceful lock foundation" />
      <div className="p-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-card border border-border rounded-sm p-6 space-y-4">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg">Current License</h3>
          <div className="grid grid-cols-2 gap-3 font-mono text-sm">
            <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs text-muted-foreground uppercase">Status</div><div>{license?.status || "—"}</div></div>
            <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs text-muted-foreground uppercase">Tier</div><div>{license?.tier || "—"}</div></div>
            <div className="border border-border rounded-sm px-3 py-2 col-span-2"><div className="text-xs text-muted-foreground uppercase">Expires</div><div>{license?.expires_at || "—"}</div></div>
          </div>
          <div className="border border-border rounded-sm p-3 font-mono text-xs space-y-2">
            {Object.entries(license?.feature_flags || {}).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between"><span className="text-muted-foreground uppercase">{key.replace(/_/g, " ")}</span><span className={value ? "text-primary" : "text-destructive"}>{value ? "Enabled" : "Locked"}</span></div>
            ))}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-6 space-y-4">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg">Activate / Upgrade</h3>
          <input value={form.license_key} onChange={(e) => setForm({ ...form, license_key: e.target.value })} placeholder="License key" className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
          <select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })} className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
            {['standard','enterprise'].map((tier) => <option key={tier} value={tier}>{tier}</option>)}
          </select>
          <input value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} placeholder="YYYY-MM-DD" className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
          <button onClick={activate} className="w-full min-h-12 bg-primary text-white rounded-sm font-display font-bold uppercase tracking-widest">Activate License</button>
          <div className="text-xs text-muted-foreground font-mono">Historical data and exports remain available; feature locks can be applied gracefully by tier or expiry.</div>
        </div>
      </div>
    </Layout>
  );
}
