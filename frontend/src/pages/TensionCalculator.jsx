import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { Calculator, CheckCircle2, XCircle } from "lucide-react";

const FIELDS = [
  { key: "jacking_force_kip", label: "Jacking Force / Strand (kip)", def: 43.94 },
  { key: "bed_length_ft", label: "Bed / Strand Length (ft)", def: 400 },
  { key: "strand_area_in2", label: "Strand Area (in²)", def: 0.217 },
  { key: "modulus_ksi", label: "Modulus of Elasticity (ksi)", def: 28500 },
  { key: "measured_elongation_in", label: "Measured Elongation (in)", def: "" },
];

export default function TensionCalculator() {
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState("");
  const [vals, setVals] = useState(Object.fromEntries(FIELDS.map((f) => [f.key, f.def])));
  const [result, setResult] = useState(null);
  const selectedBeam = useMemo(() => beams.find((beam) => beam.id === beamId), [beams, beamId]);

  useEffect(() => {
    api.get("/beams").then((res) => {
      setBeams(res.data);
      setBeamId(res.data[0]?.id || "");
    });
  }, []);

  useEffect(() => {
    if (!selectedBeam) return;
    const ref = selectedBeam.product_type?.blueprint?.tension_reference || {};
    setVals((current) => ({
      ...current,
      bed_length_ft: selectedBeam.length_ft || current.bed_length_ft,
      jacking_force_kip: ref.jacking_force_kip ?? current.jacking_force_kip,
      strand_area_in2: ref.strand_area_in2 ?? current.strand_area_in2,
    }));
  }, [selectedBeam]);

  const calc = async () => {
    const payload = {
      jacking_force_kip: parseFloat(vals.jacking_force_kip) || 0,
      bed_length_ft: parseFloat(vals.bed_length_ft) || 0,
      strand_area_in2: parseFloat(vals.strand_area_in2) || 0,
      modulus_ksi: parseFloat(vals.modulus_ksi) || 0,
      measured_elongation_in: vals.measured_elongation_in === "" ? null : parseFloat(vals.measured_elongation_in),
    };
    const { data } = await api.post("/tension/calculate", payload);
    setResult(data);
  };

  const within = result?.within_tolerance;

  return (
    <Layout>
      <PageHeader title="Tension Calculator" subtitle="Strand elongation & ±5% tension validation" />
      <div className="p-8 grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-5xl">
        {/* Inputs */}
        <div className="bg-card border border-border rounded-sm p-8">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-6 flex items-center gap-2"><Calculator className="w-5 h-5 text-primary" /> Inputs</h3>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Blueprint Reference Beam</label>
              <select value={beamId} onChange={(e) => setBeamId(e.target.value)} className="mt-1 w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm">
                {beams.map((beam) => <option key={beam.id} value={beam.id}>{beam.mark} · {beam.length_ft}ft · {beam.blueprint_source?.status || "legacy_seed"}</option>)}
              </select>
              {selectedBeam && (
                <div className={`mt-2 rounded-sm border px-3 py-2 text-xs font-mono ${selectedBeam.blueprint_source?.status === "locked" ? "border-primary/40 text-primary" : "border-[#FFD60055] text-[#FFD600]"}`}>
                  {selectedBeam.blueprint_source?.status === "locked"
                    ? `Using locked blueprint defaults${selectedBeam.product_type?.blueprint?.hold_downs?.length ? ` · ${selectedBeam.product_type.blueprint.hold_downs.length} hold-down stations` : ""}`
                    : "No locked blueprint reference — validate strand layout manually before relying on this calc."}
                </div>
              )}
            </div>
            {FIELDS.map((f) => (
              <div key={f.key}>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">{f.label}</label>
                <input
                  data-testid={`tc-${f.key}`}
                  type="number"
                  value={vals[f.key]}
                  onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}
                  className="mt-1 w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            ))}
            <button data-testid="tc-calculate" onClick={calc} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-sm hover:bg-white hover:text-black transition-colors duration-100">Calculate Elongation</button>
          </div>
          <p className="text-xs text-muted-foreground font-mono mt-4">ΔL = (P × L) / (A × E)</p>
        </div>

        {/* Results */}
        <div className="bg-card border border-border rounded-sm p-8" data-testid="tc-results">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-6">Results</h3>
          {!result ? (
            <div className="text-muted-foreground font-mono text-sm">Enter values and calculate to see theoretical elongation and validation.</div>
          ) : (
            <div className="space-y-6">
              <div>
                <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Theoretical Elongation</div>
                <div className="font-mono text-5xl font-bold mt-2" data-testid="tc-theoretical">{result.theoretical_elongation_in}<span className="text-2xl text-muted-foreground"> in</span></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="border border-border rounded-sm p-4">
                  <div className="text-xs font-mono text-muted-foreground">−5% BOUND</div>
                  <div className="font-mono text-xl font-bold text-white">{result.lower_bound_in}"</div>
                </div>
                <div className="border border-border rounded-sm p-4">
                  <div className="text-xs font-mono text-muted-foreground">+5% BOUND</div>
                  <div className="font-mono text-xl font-bold text-white">{result.upper_bound_in}"</div>
                </div>
              </div>

              {result.measured_elongation_in != null && (
                <div className="rounded-sm p-6 border-2" style={{ borderColor: within ? "#00E676" : "#FF3366", background: (within ? "#00E676" : "#FF3366") + "12" }} data-testid="tc-verdict">
                  <div className="flex items-center gap-3">
                    {within ? <CheckCircle2 className="w-8 h-8" style={{ color: "#00E676" }} /> : <XCircle className="w-8 h-8" style={{ color: "#FF3366" }} />}
                    <div>
                      <div className="font-display font-extrabold text-2xl uppercase tracking-wide" style={{ color: within ? "#00E676" : "#FF3366" }}>
                        {within ? "WITHIN TOLERANCE" : "OUT OF TOLERANCE"}
                      </div>
                      <div className="font-mono text-sm text-muted-foreground">
                        Measured {result.measured_elongation_in}" · Variance <span style={{ color: within ? "#00E676" : "#FF3366" }}>{result.variance_pct > 0 ? "+" : ""}{result.variance_pct}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
