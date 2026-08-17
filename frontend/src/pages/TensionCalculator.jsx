import React, { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { Calculator, CheckCircle2, XCircle, Save, Loader2 } from "lucide-react";
import { toast } from "sonner";

const STRAND_PRESETS = [
  { size: "0.5in", area: 0.153 },
  { size: "0.6in", area: 0.217 },
  { size: "0.7in", area: 0.294 },
];

const FIELDS = [
  { key: "jacking_force_kip", label: "Jacking Force / Strand (kip)", def: 43.94 },
  { key: "bed_length_ft", label: "Bed / Strand Length (ft)", def: 400 },
  { key: "strand_area_in2", label: "Strand Area (in²)", def: 0.217 },
  { key: "modulus_ksi", label: "Modulus of Elasticity (ksi)", def: 28500 },
  { key: "measured_elongation_in", label: "Measured Elongation (in)", def: "" },
];

export default function TensionCalculator() {
  const [vals, setVals] = useState(Object.fromEntries(FIELDS.map((f) => [f.key, f.def])));
  const [strandSize, setStrandSize] = useState("0.6in");
  const [numStrands, setNumStrands] = useState(1);
  const [beds, setBeds] = useState([]);
  const [bedId, setBedId] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api.get("/beds")
      .then((r) => {
        setBeds(r.data);
        if (r.data.length) setBedId(r.data[0].id);
      })
      .catch((err) => {
        console.error("[tension] beds load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beds");
      });
  }, []);

  const applyPreset = (size) => {
    const preset = STRAND_PRESETS.find((p) => p.size === size);
    setStrandSize(size);
    if (preset) setVals({ ...vals, strand_area_in2: preset.area });
  };

  const payload = () => ({
    jacking_force_kip: parseFloat(vals.jacking_force_kip) || 0,
    bed_length_ft: parseFloat(vals.bed_length_ft) || 0,
    strand_area_in2: parseFloat(vals.strand_area_in2) || 0,
    modulus_ksi: parseFloat(vals.modulus_ksi) || 0,
    measured_elongation_in: vals.measured_elongation_in === "" ? null : parseFloat(vals.measured_elongation_in),
  });

  const calc = async () => {
    setBusy("calc");
    try {
      const { data } = await api.post("/tension/calculate", payload());
      setResult(data);
    } catch (err) {
      console.error("[tension] calculate failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Calculation failed");
    } finally {
      setBusy("");
    }
  };

  const saveReport = async () => {
    if (!bedId) {
      toast.error("Select a bed to save this report");
      return;
    }
    setBusy("save");
    try {
      const body = {
        ...payload(),
        bed_id: bedId,
        strand_size: strandSize,
        num_strands: parseInt(numStrands, 10) || 1,
      };
      const { data } = await api.post("/tension-reports", body);
      setResult({
        theoretical_elongation_in: data.theoretical_elongation_in,
        measured_elongation_in: data.measured_elongation_in,
        variance_pct: data.variance_pct,
        within_tolerance: data.within_tolerance,
        lower_bound_in: +(data.theoretical_elongation_in * 0.95).toFixed(3),
        upper_bound_in: +(data.theoretical_elongation_in * 1.05).toFixed(3),
        tolerance_pct: 5.0,
      });
      toast.success("Tension report saved");
    } catch (err) {
      console.error("[tension] save report failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save report");
    } finally {
      setBusy("");
    }
  };

  const within = result?.within_tolerance;

  return (
    <Layout>
      <PageHeader title="Tension Calculator" subtitle="Strand elongation & ±5% tension validation" />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 max-w-5xl">
        <div className={`${cardClass} p-5 sm:p-8`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-6 flex items-center gap-2">
            <Calculator className="w-5 h-5 text-primary" /> Inputs
          </h3>
          <div className="space-y-4">
            <Field label="Bed">
              <select data-testid="tc-bed" value={bedId} onChange={(e) => setBedId(e.target.value)} className={inputClass}>
                {beds.map((b) => (
                  <option key={b.id} value={b.id}>Bed {b.bed_number} · {b.length_ft} ft</option>
                ))}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Strand Size">
                <select data-testid="tc-strand-size" value={strandSize} onChange={(e) => applyPreset(e.target.value)} className={inputClass}>
                  {STRAND_PRESETS.map((p) => (
                    <option key={p.size} value={p.size}>{p.size} · {p.area} in²</option>
                  ))}
                </select>
              </Field>
              <Field label="No. of Strands">
                <input data-testid="tc-num-strands" type="number" min="1" value={numStrands} onChange={(e) => setNumStrands(e.target.value)} className={inputClass} />
              </Field>
            </div>
            {FIELDS.map((f) => (
              <Field key={f.key} label={f.label}>
                <input
                  data-testid={`tc-${f.key}`}
                  type="number"
                  value={vals[f.key]}
                  onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}
                  className={inputClass}
                />
              </Field>
            ))}
            <button
              data-testid="tc-calculate"
              onClick={calc}
              disabled={busy === "calc"}
              className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {busy === "calc" && <Loader2 className="w-4 h-4 animate-spin" />}
              Calculate Elongation
            </button>
            <button
              data-testid="tc-save"
              onClick={saveReport}
              disabled={busy === "save"}
              className="w-full min-h-12 border border-[#1C2230] rounded-none flex items-center justify-center gap-2 font-semibold uppercase tracking-wider hover:border-primary hover:text-primary disabled:opacity-60"
            >
              {busy === "save" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Report
            </button>
          </div>
          <p className="text-xs text-muted-foreground font-mono mt-4">ΔL = (P × L) / (A × E) · tolerance ±5%</p>
        </div>

        <div className={`${cardClass} p-5 sm:p-8`} data-testid="tc-results">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-6">Results</h3>
          {!result ? (
            <div className="text-muted-foreground font-mono text-sm">Enter values and calculate to see theoretical elongation and validation.</div>
          ) : (
            <div className="space-y-6">
              <div>
                <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Theoretical Elongation</div>
                <div className="font-mono text-4xl sm:text-5xl font-bold mt-2" data-testid="tc-theoretical">
                  {result.theoretical_elongation_in}<span className="text-2xl text-muted-foreground"> in</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="border border-[#1C2230] rounded-none p-4">
                  <div className="text-xs font-mono text-muted-foreground">−5% BOUND</div>
                  <div className="font-mono text-xl font-bold text-white">{result.lower_bound_in}"</div>
                </div>
                <div className="border border-[#1C2230] rounded-none p-4">
                  <div className="text-xs font-mono text-muted-foreground">+5% BOUND</div>
                  <div className="font-mono text-xl font-bold text-white">{result.upper_bound_in}"</div>
                </div>
              </div>

              {result.measured_elongation_in != null && (
                <div
                  className="rounded-none p-6 border-2"
                  style={{ borderColor: within ? "#00E676" : "#FF3366", background: `${within ? "#00E676" : "#FF3366"}12` }}
                  data-testid="tc-verdict"
                >
                  <div className="flex items-center gap-3">
                    {within ? <CheckCircle2 className="w-8 h-8" style={{ color: "#00E676" }} /> : <XCircle className="w-8 h-8" style={{ color: "#FF3366" }} />}
                    <div>
                      <div className="font-display font-extrabold text-xl sm:text-2xl uppercase tracking-wide" style={{ color: within ? "#00E676" : "#FF3366" }}>
                        {within ? "WITHIN TOLERANCE" : "OUT OF TOLERANCE"}
                      </div>
                      <div className="font-mono text-sm text-muted-foreground">
                        Measured {result.measured_elongation_in}" · Variance{" "}
                        <span style={{ color: within ? "#00E676" : "#FF3366" }}>
                          {result.variance_pct > 0 ? "+" : ""}{result.variance_pct}%
                        </span>
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
