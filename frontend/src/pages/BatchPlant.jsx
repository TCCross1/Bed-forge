import React, { useEffect, useState } from "react";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { toast } from "sonner";

export default function BatchPlant() {
  const [records, setRecords] = useState([]);
  const [pours, setPours] = useState([]);
  const [beams, setBeams] = useState([]);
  const [form, setForm] = useState({ pour_id: "", ticket_number: "", mix_design: "8500psi HPC", ambient_temp_f: 75, concrete_temp_f: 72, humidity_pct: 55, wind_mph: 5, weather: "Clear", notes: "", ingredientsText: "Type III Cement|940|938\nCoarse Aggregate|1780|1788", admixturesText: "Mid-range Water Reducer|112", cylindersText: "CYL-NEW-A|18|6100" });

  const parseLines = (text, keys) =>
    text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split("|").map((item) => item.trim());
        return Object.fromEntries(keys.map((key, index) => [key, parts[index] || ""]));
      });

  const load = () => Promise.all([api.get("/batch-records"), api.get("/pours"), api.get("/beams")]).then(([recordsRes, poursRes, beamsRes]) => {
    setRecords(recordsRes.data);
    setPours(poursRes.data);
    setBeams(beamsRes.data);
    setForm((current) => ({ ...current, pour_id: current.pour_id || poursRes.data[0]?.id || "" }));
  });

  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/batch-records", {
        ...form,
        beam_ids: beams.filter((beam) => beam.pour_id === form.pour_id).map((beam) => beam.id),
        ingredients: parseLines(form.ingredientsText, ["name", "target_lb", "actual_lb"]),
        admixtures: parseLines(form.admixturesText, ["name", "dosage_oz"]),
        cylinders: parseLines(form.cylindersText, ["id", "age_hr", "strength_psi"]),
      });
      await load();
      toast.success("Batch record created");
    } catch {
      toast.error("Failed to create batch record");
    }
  };

  return (
    <Layout>
      <PageHeader title="Batch Plant" subtitle="Mix records, environmental capture, ingredients, and permanent pour history" />
      <div className="p-8 grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="bg-card border border-border rounded-sm p-6 space-y-4">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg">Record Batch Ticket</h3>
          <select value={form.pour_id} onChange={(e) => setForm({ ...form, pour_id: e.target.value })} className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
            {pours.map((pour) => <option key={pour.id} value={pour.id}>{pour.pour_number}</option>)}
          </select>
          <input value={form.ticket_number} onChange={(e) => setForm({ ...form, ticket_number: e.target.value })} placeholder="Ticket number" className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
          <input value={form.mix_design} onChange={(e) => setForm({ ...form, mix_design: e.target.value })} placeholder="Mix design" className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
          <div className="grid grid-cols-2 gap-3">
            {[
              ["ambient_temp_f", "Ambient °F"],
              ["concrete_temp_f", "Concrete °F"],
              ["humidity_pct", "Humidity %"],
              ["wind_mph", "Wind MPH"],
            ].map(([key, label]) => (
              <input key={key} type="number" value={form[key]} onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} placeholder={label} className="bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
            ))}
          </div>
          <input value={form.weather} onChange={(e) => setForm({ ...form, weather: e.target.value })} placeholder="Weather" className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
          <textarea value={form.ingredientsText} onChange={(e) => setForm({ ...form, ingredientsText: e.target.value })} placeholder="Ingredient|Target|Actual" rows={3} className="w-full bg-background border border-border rounded-sm px-3 py-2 font-mono text-xs" />
          <textarea value={form.admixturesText} onChange={(e) => setForm({ ...form, admixturesText: e.target.value })} placeholder="Admixture|Dosage" rows={2} className="w-full bg-background border border-border rounded-sm px-3 py-2 font-mono text-xs" />
          <textarea value={form.cylindersText} onChange={(e) => setForm({ ...form, cylindersText: e.target.value })} placeholder="Cylinder|Age Hr|Strength PSI" rows={2} className="w-full bg-background border border-border rounded-sm px-3 py-2 font-mono text-xs" />
          <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Notes" rows={3} className="w-full bg-background border border-border rounded-sm px-3 py-2 font-mono text-sm" />
          <button onClick={create} className="w-full min-h-12 bg-primary text-white rounded-sm font-display font-bold uppercase tracking-widest">Save Batch Record</button>
        </div>
        <div className="xl:col-span-2 bg-card border border-border rounded-sm p-6">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Permanent Batch History</h3>
          <div className="space-y-3">
            {records.map((record) => (
              <div key={record.id} className="border border-border rounded-sm p-4 grid grid-cols-1 md:grid-cols-6 gap-3 font-mono text-sm">
                <div><div className="text-xs text-muted-foreground uppercase">Ticket</div><div>{record.ticket_number}</div></div>
                <div><div className="text-xs text-muted-foreground uppercase">Mix</div><div>{record.mix_design}</div></div>
                <div><div className="text-xs text-muted-foreground uppercase">Ambient</div><div>{record.ambient_temp_f}°F</div></div>
                <div><div className="text-xs text-muted-foreground uppercase">Concrete</div><div>{record.concrete_temp_f}°F</div></div>
                <div><div className="text-xs text-muted-foreground uppercase">Humidity</div><div>{record.humidity_pct}%</div></div>
                <div><div className="text-xs text-muted-foreground uppercase">Wind</div><div>{record.wind_mph} mph</div></div>
              </div>
            ))}
            {records.length === 0 && <div className="text-sm text-muted-foreground font-mono">No batch records yet.</div>}
          </div>
        </div>
      </div>
    </Layout>
  );
}
