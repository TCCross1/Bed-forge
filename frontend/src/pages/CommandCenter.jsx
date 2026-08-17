import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Download, Loader2, Search, Shield, UserX } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { ROLE_LABELS, isExec } from "../lib/constants";
import { useAuth } from "../context/AuthContext";

const TABS = [
  { id: "search", label: "Search" },
  { id: "people", label: "People" },
  { id: "devices", label: "Devices" },
  { id: "audit", label: "Audit" },
  { id: "security", label: "Security" },
  { id: "overrides", label: "Overrides" },
  { id: "export", label: "Export" },
];

const DATASETS = ["jobs", "beams", "inspections", "tension_reports", "camber_readings", "finish_sheets", "pre_delivery", "strand_rolls", "audit_log"];

export default function CommandCenter() {
  const { user } = useAuth();
  const exec = isExec(user?.role);
  const [tab, setTab] = useState("search");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState(null);
  const [people, setPeople] = useState([]);
  const [devices, setDevices] = useState([]);
  const [audit, setAudit] = useState([]);
  const [overrides, setOverrides] = useState([]);
  const [security, setSecurity] = useState(null);
  const [busy, setBusy] = useState("");
  const [newUser, setNewUser] = useState({ name: "", email: "", password: "", role: "qc_tech" });
  const [override, setOverride] = useState({ kind: "strand_tension", target_id: "", reason: "", hours: 8 });

  const loadTab = useCallback(async (id) => {
    try {
      if (id === "people") {
        const { data } = await api.get("/control/users");
        setPeople(data.users || []);
      }
      if (id === "devices") {
        const { data } = await api.get("/control/devices");
        setDevices(data.devices || []);
      }
      if (id === "audit") {
        const { data } = await api.get("/control/audit?limit=150");
        setAudit(data.events || []);
      }
      if (id === "security") {
        const { data } = await api.get("/control/security");
        setSecurity(data);
      }
      if (id === "overrides") {
        const { data } = await api.get("/control/overrides");
        setOverrides(data.overrides || []);
      }
    } catch (err) {
      console.error("[command] load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load command data");
    }
  }, []);

  useEffect(() => {
    if (exec) loadTab(tab);
  }, [tab, exec, loadTab]);

  if (!exec) {
    return (
      <Layout>
        <PageHeader title="Command" subtitle="Plant manager access required" />
        <div className="p-8 text-sm text-muted-foreground">This desk is only for plant managers and executives.</div>
      </Layout>
    );
  }

  const search = async (e) => {
    e.preventDefault();
    setBusy("search");
    try {
      const { data } = await api.get(`/control/search?q=${encodeURIComponent(q)}`);
      setHits(data);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Search failed");
    } finally {
      setBusy("");
    }
  };

  const createPerson = async (e) => {
    e.preventDefault();
    setBusy("user");
    try {
      await api.post("/control/users", newUser);
      toast.success("Account created — they must change password at first sign-in");
      setNewUser({ name: "", email: "", password: "", role: "qc_tech" });
      await loadTab("people");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Could not create user");
    } finally {
      setBusy("");
    }
  };

  const patchUser = async (id, body) => {
    try {
      await api.patch(`/control/users/${id}`, body);
      await loadTab("people");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Update failed");
    }
  };

  const revoke = async (id) => {
    setBusy(id);
    try {
      await api.post(`/control/users/${id}/revoke`);
      toast.success("Sessions and devices revoked");
      await loadTab("people");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Revoke failed");
    } finally {
      setBusy("");
    }
  };

  const saveSecurity = async (e) => {
    e.preventDefault();
    setBusy("sec");
    try {
      const { data } = await api.patch("/control/security", {
        ...security,
        ip_allowlist: String(security.ip_allowlist_text || (security.ip_allowlist || []).join("\n"))
          .split(/[\n,]+/)
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setSecurity({ ...data, ip_allowlist_text: (data.ip_allowlist || []).join("\n") });
      toast.success("Security settings saved — logged");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Save failed");
    } finally {
      setBusy("");
    }
  };

  const submitOverride = async (e) => {
    e.preventDefault();
    setBusy("ov");
    try {
      await api.post("/control/override", override);
      toast.success("Override written to the audit log");
      setOverride({ ...override, target_id: "", reason: "" });
      await loadTab("overrides");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Override failed");
    } finally {
      setBusy("");
    }
  };

  const download = async (path, filename) => {
    setBusy(filename);
    try {
      const res = await api.get(path, { responseType: "blob" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(res.data);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success("Download started — this export is audited");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Export failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Plant command"
        subtitle="Upper management control — every privileged action is logged"
        right={
          <Link to="/guide" className="min-h-12 px-4 border border-[#1C2230] flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary">
            <BookOpen className="w-4 h-4" /> Tutorial
          </Link>
        }
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-6xl">
        <div className={`${cardClass} p-1 mb-4 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 print:hidden`}>
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`min-h-12 font-condensed uppercase tracking-wider text-xs ${tab === item.id ? "bg-primary text-white" : "text-muted-foreground"}`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === "search" && (
          <div className={`${cardClass} p-4 sm:p-6`} data-testid="command-search">
            <form onSubmit={search} className="flex flex-col sm:flex-row gap-2 mb-4">
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Job, beam mark, heat, person…" className={inputClass} />
              <button type="submit" className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center justify-center gap-2">
                {busy === "search" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Search
              </button>
            </form>
            {hits && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                {["jobs", "beams", "pours", "strand_rolls", "users"].map((key) => (
                  <div key={key}>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">{key.replace("_", " ")}</div>
                    {(hits[key] || []).length === 0 ? <p className="text-muted-foreground">None</p> : (hits[key] || []).map((row) => (
                      <div key={row.id} className="py-1 border-b border-[#1C2230] font-mono">
                        {row.job_number || row.mark || row.pour_number || row.heat_number || row.email} {row.name ? `· ${row.name}` : ""}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "people" && (
          <div className="space-y-4">
            <form onSubmit={createPerson} className={`${cardClass} p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3`}>
              <Field label="Name"><input className={inputClass} value={newUser.name} onChange={(e) => setNewUser({ ...newUser, name: e.target.value })} required /></Field>
              <Field label="Email"><input type="email" className={inputClass} value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} required /></Field>
              <Field label="Temp password"><input type="password" className={inputClass} value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} required minLength={10} /></Field>
              <Field label="Role">
                <select className={inputClass} value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                  {Object.keys(ROLE_LABELS).map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}
                </select>
              </Field>
              <button type="submit" disabled={busy === "user"} className="min-h-12 self-end bg-primary text-white font-display font-bold uppercase tracking-widest">Create</button>
            </form>
            <div className={`${cardClass} overflow-x-auto`}>
              <table className="w-full text-sm">
                <thead className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                  <tr>{["Name", "Email", "Role", "Status", "Actions"].map((h) => <th key={h} className="text-left p-3">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {people.map((person) => (
                    <tr key={person.id} className="border-t border-[#1C2230]">
                      <td className="p-3">{person.name}</td>
                      <td className="p-3 font-mono text-xs">{person.email}</td>
                      <td className="p-3">
                        <select className={`${inputClass} min-h-10`} value={person.role} onChange={(e) => patchUser(person.id, { role: e.target.value })}>
                          {Object.keys(ROLE_LABELS).map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}
                        </select>
                      </td>
                      <td className="p-3 font-mono text-xs" style={{ color: person.disabled ? "#FF3366" : "#00E676" }}>{person.disabled ? "DISABLED" : "ACTIVE"}</td>
                      <td className="p-3 flex flex-wrap gap-2">
                        <button type="button" onClick={() => patchUser(person.id, { disabled: !person.disabled })} className="text-xs uppercase tracking-wider border border-[#1C2230] min-h-10 px-3">
                          {person.disabled ? "Enable" : "Disable"}
                        </button>
                        <button type="button" onClick={() => revoke(person.id)} className="text-xs uppercase tracking-wider border border-[#1C2230] min-h-10 px-3 flex items-center gap-1">
                          <UserX className="w-3 h-3" /> Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "devices" && (
          <div className={`${cardClass} overflow-x-auto`}>
            <table className="w-full text-sm">
              <thead className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                <tr>{["Model", "Class", "Platform", "User", "Status", ""].map((h) => <th key={h} className="text-left p-3">{h}</th>)}</tr>
              </thead>
              <tbody>
                {devices.map((dev) => (
                  <tr key={dev.id} className="border-t border-[#1C2230]">
                    <td className="p-3">{dev.model || "—"}</td>
                    <td className="p-3 font-mono text-xs">{dev.device_class}</td>
                    <td className="p-3 font-mono text-xs">{dev.platform}</td>
                    <td className="p-3 font-mono text-xs">{dev.user_id}</td>
                    <td className="p-3" style={{ color: dev.revoked ? "#FF3366" : "#00E676" }}>{dev.revoked ? "REVOKED" : "ACTIVE"}</td>
                    <td className="p-3">
                      {!dev.revoked && (
                        <button type="button" onClick={async () => { await api.post(`/control/devices/${dev.id}/revoke`); loadTab("devices"); }} className="text-xs uppercase tracking-wider border border-[#1C2230] min-h-10 px-3">Revoke</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "audit" && (
          <div className={`${cardClass} overflow-x-auto`} data-testid="command-audit">
            <table className="w-full text-sm">
              <thead className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                <tr>{["When", "Who", "Action", "Target", "IP"].map((h) => <th key={h} className="text-left p-3">{h}</th>)}</tr>
              </thead>
              <tbody>
                {audit.map((row) => (
                  <tr key={row.id} className="border-t border-[#1C2230]">
                    <td className="p-3 font-mono text-xs whitespace-nowrap">{String(row.created_at || "").slice(0, 19)}</td>
                    <td className="p-3">{row.actor_email}</td>
                    <td className="p-3 font-mono text-xs">{row.action}</td>
                    <td className="p-3 font-mono text-xs">{row.entity_type} {row.entity_id}</td>
                    <td className="p-3 font-mono text-xs">{row.ip}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "security" && security && (
          <form onSubmit={saveSecurity} className={`${cardClass} p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-2 gap-4`}>
            <Field label="Session minutes">
              <input type="number" className={inputClass} value={security.session_minutes} onChange={(e) => setSecurity({ ...security, session_minutes: Number(e.target.value) })} />
            </Field>
            <Field label="Idle timeout minutes">
              <input type="number" className={inputClass} value={security.idle_minutes} onChange={(e) => setSecurity({ ...security, idle_minutes: Number(e.target.value) })} />
            </Field>
            <Field label="Camber tolerance (in)">
              <input type="number" step="0.001" className={inputClass} value={security.camber_tolerance_in} onChange={(e) => setSecurity({ ...security, camber_tolerance_in: Number(e.target.value) })} />
            </Field>
            <Field label="Length tolerance (in)">
              <input type="number" step="0.01" className={inputClass} value={security.length_tolerance_in} onChange={(e) => setSecurity({ ...security, length_tolerance_in: Number(e.target.value) })} />
            </Field>
            <Field label="Retention days">
              <input type="number" className={inputClass} value={security.retention_days} onChange={(e) => setSecurity({ ...security, retention_days: Number(e.target.value) })} />
            </Field>
            <div className="flex items-center gap-3 min-h-12">
              <input type="checkbox" checked={Boolean(security.office_ip_enforced)} onChange={(e) => setSecurity({ ...security, office_ip_enforced: e.target.checked })} />
              <span className="text-sm">Require office/VPN IP for command actions</span>
            </div>
            <div className="flex items-center gap-3 min-h-12">
              <input type="checkbox" checked={Boolean(security.bind_device)} onChange={(e) => setSecurity({ ...security, bind_device: e.target.checked })} />
              <span className="text-sm">Bind sessions to device</span>
            </div>
            <div className="flex items-center gap-3 min-h-12">
              <input type="checkbox" checked={Boolean(security.legal_hold)} onChange={(e) => setSecurity({ ...security, legal_hold: e.target.checked })} />
              <span className="text-sm">Legal hold — block purge</span>
            </div>
            <div className="sm:col-span-2">
              <Field label="IP allow-list (CIDR, one per line)">
                <textarea
                  className={`${inputClass} min-h-[120px] py-3`}
                  value={security.ip_allowlist_text ?? (security.ip_allowlist || []).join("\n")}
                  onChange={(e) => setSecurity({ ...security, ip_allowlist_text: e.target.value })}
                  placeholder="10.0.0.0/8"
                />
              </Field>
            </div>
            <button type="submit" disabled={busy === "sec"} className="min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest sm:col-span-2">
              {busy === "sec" ? "Saving…" : "Save security settings"}
            </button>
          </form>
        )}

        {tab === "overrides" && (
          <div className="space-y-4">
            <form onSubmit={submitOverride} className={`${cardClass} p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-2 gap-3`}>
              <Field label="Kind">
                <select className={inputClass} value={override.kind} onChange={(e) => setOverride({ ...override, kind: e.target.value })}>
                  <option value="strand_tension">Strand tension gate</option>
                  <option value="spec_unlock">Unlock BeamSpec</option>
                  <option value="qc_force">Force QC passed</option>
                </select>
              </Field>
              <Field label="Target id (bed, spec, or beam)">
                <input className={inputClass} value={override.target_id} onChange={(e) => setOverride({ ...override, target_id: e.target.value })} required />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Written reason (required, audited)">
                  <textarea className={`${inputClass} min-h-[80px] py-3`} value={override.reason} onChange={(e) => setOverride({ ...override, reason: e.target.value })} required minLength={8} />
                </Field>
              </div>
              <button type="submit" className="min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest">Issue override</button>
            </form>
            <div className={`${cardClass} p-4 space-y-2`}>
              {overrides.map((row) => (
                <div key={row.id} className="border-b border-[#1C2230] py-2 text-sm flex justify-between gap-3">
                  <div>
                    <div className="font-mono text-xs">{row.kind} · {row.target_id}</div>
                    <div className="text-muted-foreground">{row.reason}</div>
                  </div>
                  {!row.revoked && (
                    <button type="button" onClick={async () => { await api.post(`/control/overrides/${row.id}/revoke`); loadTab("overrides"); }} className="text-xs uppercase tracking-wider border border-[#1C2230] min-h-10 px-3">Revoke</button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "export" && (
          <div className={`${cardClass} p-4 sm:p-6 space-y-3`}>
            <p className="text-sm text-muted-foreground">Every download is written to the audit log. Restore is an offline procedure onto clean hardware — never onto a host that was attacked.</p>
            <button type="button" onClick={() => download("/control/backup", "bedforge-backup.zip")} className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center gap-2">
              <Download className="w-4 h-4" /> Full plant backup
            </button>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {DATASETS.map((name) => (
                <button key={name} type="button" onClick={() => download(`/control/export/${name}`, `${name}.json`)} className="min-h-12 border border-[#1C2230] uppercase tracking-wider text-xs hover:border-primary">
                  {name.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
              <Shield className="w-4 h-4 text-[#C9A227]" /> Passwords, tokens, and photo bytes are stripped from exports.
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
