import React, { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass, ARMeasureLink } from "../components/Layout";
import TensionTwin from "../components/TensionTwin";
import {
  HOLD_DOWN_STATUS_COLORS,
  STRAND_TENSION_COLORS,
  holdDownColor,
  strandTensionColor,
  strandTensionStatus,
} from "../lib/beamSpec";
import { Calculator, CheckCircle2, XCircle, Save, Loader2, ScanBarcode } from "lucide-react";
import { toast } from "sonner";
import { toastNcrFromResponse } from "../lib/ncr";
import { useDevice } from "../context/DeviceContext";
import { useOpenJob } from "../context/OpenJobContext";
import StrandRolls from "./StrandRolls";
import StrandQcPhotos from "./StrandQcPhotos";

const STRAND_PRESETS = [
  { size: "0.5in oversize", area: 0.167 },
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

const HD_STATES = ["pending", "installed", "stressed", "released", "inspected", "verified", "issue"];

function SummaryChip({ label, value, color, testid }) {
  return (
    <div className="border border-[#1C2230] px-3 py-2 min-h-12 flex flex-col justify-center" data-testid={testid}>
      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className="font-mono text-lg font-bold" style={{ color }}>{value}</div>
    </div>
  );
}

export default function TensionCalculator() {
  const device = useDevice();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "tension";
  const { openJob, setActiveMark } = useOpenJob();
  const [beams, setBeams] = useState([]);
  const [selectedId, setSelectedId] = useState(params.get("beam") || "");
  const [twin, setTwin] = useState(null);
  const [view, setView] = useState("end");
  const [selected, setSelected] = useState(null);
  const [measured, setMeasured] = useState("");
  const [jacking, setJacking] = useState("");
  const [notes, setNotes] = useState("");
  const [hdStatus, setHdStatus] = useState("pending");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");

  const [vals, setVals] = useState(Object.fromEntries(FIELDS.map((f) => [f.key, f.def])));
  const [strandSize, setStrandSize] = useState("0.6in");
  const [numStrands, setNumStrands] = useState(1);
  const [beds, setBeds] = useState([]);
  const [bedId, setBedId] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.get("/beams", { params: openJob?.id ? { job_id: openJob.id } : {} })
      .then((r) => {
        setBeams(r.data || []);
        setSelectedId((cur) => cur || r.data?.[0]?.id || "");
      })
      .catch((err) => {
        console.error("[tension] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
    api.get("/beds")
      .then((r) => {
        setBeds(r.data);
        if (r.data.length) setBedId(r.data[0].id);
      })
      .catch((err) => {
        console.error("[tension] beds load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beds");
      });
  }, [openJob?.id]);

  useEffect(() => {
    const mark = beams.find((item) => item.id === selectedId)?.mark || "";
    setActiveMark(mark);
  }, [beams, selectedId, setActiveMark]);

  const loadTwin = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/beams/${id}/tension-twin`);
      setTwin(data);
      if (data.bed?.id) setBedId(data.bed.id);
      const strandMeta = data.spec?.strand_spec || {};
      const firstStrand = data.strands?.[0] || {};
      setVals((cur) => ({
        ...cur,
        bed_length_ft: data.bed_length_ft || cur.bed_length_ft,
        jacking_force_kip: strandMeta.final_pull_kip || firstStrand.jacking_force || firstStrand.jacking_kip || cur.jacking_force_kip,
        strand_area_in2: strandMeta.area_in2 || firstStrand.area_in2 || cur.strand_area_in2,
        modulus_ksi: firstStrand.modulus_ksi || cur.modulus_ksi,
      }));
      if (strandMeta.area_in2 || firstStrand.area_in2) setStrandSize(firstStrand.size || "0.5in oversize");
      if (data.strands?.length) setNumStrands(data.strands.length);
    } catch (err) {
      console.error("[tension] twin load failed", err);
      setTwin(null);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "No BeamSpec twin for this beam");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTwin(selectedId);
    setSelected(null);
  }, [selectedId, loadTwin]);

  const pick = (next) => {
    setSelected(next);
    if (next?.kind === "strand") {
      setMeasured(next.item.measured_elongation != null ? String(next.item.measured_elongation) : "");
      setJacking(String(next.item.jacking_force || next.item.jacking_kip || ""));
      setNotes(next.item.notes || "");
      setView((cur) => (cur === "side" ? cur : "end"));
    }
    if (next?.kind === "hold_down") {
      setHdStatus(next.item.status || "pending");
      setNotes(next.item.notes || "");
      setView("side");
    }
  };

  const saveStrand = async (na = false) => {
    if (gated) {
      toast.error(gate.message || "Scan a mill tag before tensioning");
      return;
    }
    if (!twin?.spec?.id || selected?.kind !== "strand") return;
    setBusy("strand");
    try {
      const { data } = await api.post(
        `/beam-specs/${twin.spec.id}/strands/${selected.item.id}/tension`,
        {
          measured_elongation_in: na ? null : (measured === "" ? null : parseFloat(measured)),
          jacking_force_kip: jacking === "" ? null : parseFloat(jacking),
          bed_length_ft: twin.bed_length_ft,
          na,
          notes,
        }
      );
      toast.success(na ? "Strand marked N/A" : (data.within_tolerance ? "WITHIN ±5%" : data.measured_elongation == null ? "Theoretical stored" : "OUT OF TOLERANCE"));
      toastNcrFromResponse(data);
      await loadTwin(selectedId);
      setSelected({ kind: "strand", item: { ...selected.item, ...data } });
    } catch (err) {
      console.error("[tension] strand save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save strand");
    } finally {
      setBusy("");
    }
  };

  const saveHoldDown = async () => {
    if (gated) {
      toast.error(gate.message || "Scan a mill tag before tensioning");
      return;
    }
    if (!twin?.spec?.id || selected?.kind !== "hold_down") return;
    setBusy("hold");
    try {
      const { data } = await api.post(
        `/beam-specs/${twin.spec.id}/hold-downs/${selected.item.id}/check`,
        { status: hdStatus, notes }
      );
      toast.success(`Hold-down ${hdStatus}`);
      toastNcrFromResponse(data);
      await loadTwin(selectedId);
      setSelected({ kind: "hold_down", item: data });
    } catch (err) {
      console.error("[tension] hold-down save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save hold-down");
    } finally {
      setBusy("");
    }
  };

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
    if (gated) {
      toast.error(gate.message || "Scan a mill tag before tensioning");
      return;
    }
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
      toastNcrFromResponse(data);
    } catch (err) {
      console.error("[tension] save report failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save report");
    } finally {
      setBusy("");
    }
  };

  const within = result?.within_tolerance;
  const summary = twin?.summary || {};
  const spec = twin?.spec;
  const gate = twin?.strand_gate || { ok: true, rolls: [] };
  const gated = gate.ok === false;

  return (
    <Layout>
      <PageHeader
        title="Tension / Strands"
        subtitle={`${openJob?.job_number || "Open a job"} · mill tags, QC photos, and elongation on this pour`}
        right={
          <div className="flex flex-wrap gap-2 justify-end">
            <ARMeasureLink beamId={selectedId} purpose="layout" />
            {[["tension", "Tension"], ["rolls", "Rolls"], ["photos", "QC Photos"]].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  const next = new URLSearchParams(params);
                  if (value === "tension") next.delete("tab");
                  else next.set("tab", value);
                  setParams(next);
                }}
                className={`min-h-12 px-4 border rounded-none text-sm font-semibold uppercase tracking-wider ${tab === value ? "border-primary bg-primary text-white" : "border-[#1C2230] hover:border-primary hover:text-primary"}`}
                data-testid={`tension-tab-${value}`}
              >
                {label}
              </button>
            ))}
          </div>
        }
      />

      {tab === "rolls" ? (
        <div className="p-4 sm:p-6 lg:p-8"><StrandRolls embedded /></div>
      ) : tab === "photos" ? (
        <div className="p-4 sm:p-6 lg:p-8"><StrandQcPhotos /></div>
      ) : (
      <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
        {gated && (
          <div className={`${cardClass} p-4 border-[#FF3366]`} data-testid="strand-gate-block">
            <div className="font-display font-bold uppercase tracking-wider text-[#FF3366]">Tensioning locked</div>
            <p className="text-sm text-muted-foreground mt-1">{gate.message || "Scan and confirm a mill tag before stressing this bed."}</p>
            <Link to="/tension?tab=rolls" className="inline-flex mt-3 min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest items-center gap-2">
              <ScanBarcode className="w-4 h-4" /> Scan mill tag
            </Link>
          </div>
        )}
        {!gated && gate.rolls?.length > 0 && (
          <div className={`${cardClass} p-4`} data-testid="strand-gate-ok">
            <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Mill heat on this bed</div>
            <div className="font-mono text-sm mt-1 text-[#00E676]">
              {gate.rolls.map((r) => `HEAT ${r.heat_number}${r.reel_number ? ` · REEL ${r.reel_number}` : ""}`).join("  ·  ")}
            </div>
          </div>
        )}
        <div className={`${cardClass} p-4 grid grid-cols-1 md:grid-cols-3 gap-3`}>
          <Field label="Beam">
            <select data-testid="tension-beam-select" value={selectedId} onChange={(e) => setSelectedId(e.target.value)} className={inputClass}>
              {beams.map((b) => (
                <option key={b.id} value={b.id}>{b.mark} · {b.length_ft} ft</option>
              ))}
            </select>
          </Field>
          <div className="md:col-span-2 grid grid-cols-2 gap-2 content-end">
            {[
              { key: "end", label: "End View" },
              { key: "side", label: "Side / Drape" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                data-testid={`tension-view-${item.key}`}
                onClick={() => setView(item.key)}
                className={`min-h-12 font-condensed uppercase tracking-wider text-sm border border-[#1C2230] ${view === item.key ? "bg-primary text-white" : "text-muted-foreground"}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <SummaryChip
            label="Strands complete"
            value={`${summary.strands_complete || 0}/${summary.strands_total || 0}`}
            color="#2979FF"
            testid="tension-summary-strands"
          />
          <SummaryChip
            label="Hold-downs verified"
            value={`${summary.hold_downs_verified || 0}/${summary.hold_downs_total || 0}`}
            color="#C9A227"
            testid="tension-summary-holddowns"
          />
          <SummaryChip label="Bed length" value={`${twin?.bed_length_ft || "—"} ft`} color="#FFFFFF" testid="tension-summary-bed" />
          <SummaryChip label="Spec" value={(spec?.status || "none").toUpperCase()} color={spec?.status === "locked" ? "#00E676" : "#FFD600"} testid="tension-summary-spec" />
        </div>

        <div className="flex flex-wrap gap-2">
          {Object.entries(STRAND_TENSION_COLORS).map(([key, color]) => (
            <span key={key} className="text-[10px] font-mono px-2 py-1 border border-[#1C2230]" style={{ color }}>
              STRAND {key === "pass" ? "±5%" : key === "fail" ? "OUT" : key.toUpperCase()}
            </span>
          ))}
          {Object.entries(HOLD_DOWN_STATUS_COLORS).filter(([k]) => ["pending", "verified", "issue", "stressed"].includes(k)).map(([key, color]) => (
            <span key={key} className="text-[10px] font-mono px-2 py-1 border border-[#1C2230]" style={{ color }}>
              HD {key.toUpperCase()}
            </span>
          ))}
        </div>
        {spec?.strand_spec && (
          <div className={`${cardClass} p-4 grid grid-cols-1 md:grid-cols-4 gap-3`} data-testid="tension-strand-spec">
            <div className="md:col-span-2">
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Shop drawing</div>
              <div className="font-display font-bold uppercase tracking-wider">{spec.strand_spec.shop_drawing_title || spec.source_drawing || "Locked BeamSpec"}</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Strand</div>
              <div className="font-mono text-sm">{spec.strand_spec.diameter_label} · {spec.strand_spec.grade_ksi}K · As {spec.strand_spec.area_in2} in²</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Final pull</div>
              <div className="font-mono text-sm">{spec.strand_spec.final_pull_lbs?.toLocaleString?.() || spec.strand_spec.final_pull_lbs} lb · {spec.strand_spec.aashto}</div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-4">
          <div className={`${cardClass} overflow-hidden`}>
            <div className="px-4 py-3 border-b border-[#1C2230] font-display font-bold uppercase tracking-wider">
              {spec
                ? `${spec.product_name} · ${spec.beam_mark} · ${view === "end" ? "Marked End strand pattern" : "Draped profile + H-56-S"}`
                : "Select a beam with a locked BeamSpec"}
            </div>
            {loading ? (
              <div className={`${device.field ? "h-[420px]" : "h-[560px]"} flex items-center justify-center text-muted-foreground`}>
                <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading tension twin…
              </div>
            ) : spec ? (
              <TensionTwin
                spec={spec}
                strands={twin.strands || []}
                holdDowns={twin.hold_downs || []}
                view={view}
                selected={selected}
                onSelect={pick}
                height={device.field ? 420 : 560}
              />
            ) : (
              <div className="h-[320px] flex items-center justify-center text-sm font-mono text-muted-foreground px-6 text-center">
                Upload a shop drawing and lock the BeamSpec so this beam has a unique strand pattern and hold-down layout.
              </div>
            )}
          </div>

          <div className={`${cardClass} p-5 sm:p-6`} data-testid="tension-capture-panel">
            {!selected && (
              <div className="text-sm font-mono text-muted-foreground">Tap a strand or hold-down on the twin.</div>
            )}
            {selected?.kind === "strand" && (
              <div className="space-y-4">
                <h3 className="font-display font-bold uppercase tracking-wider text-lg" style={{ color: strandTensionColor(selected.item) }}>
                  Strand {selected.item.number}
                </h3>
                <div className="text-[11px] font-mono text-muted-foreground space-y-1">
                  <div>ROW {selected.item.row} · COL {selected.item.column} · {selected.item.draped || selected.item.detensioning === "draped" ? "DRAPED" : "STRAIGHT"}</div>
                  <div>
                    X {selected.item.x_in ?? selected.item.offset_in}" CL
                    {selected.item.draped || selected.item.detensioning === "draped"
                      ? ` · END ${selected.item.drape_peak_in ?? selected.item.y_in}" · HOLD ${selected.item.hold_down_y_in ?? selected.item.soffit_in}"`
                      : ` · Y ${selected.item.y_in ?? selected.item.soffit_in}" SOFFIT`}
                  </div>
                  <div>THEO {selected.item.theoretical_elongation ?? "—"}" · {selected.item.size} · {selected.item.area_in2} in²</div>
                  <div>STATUS {strandTensionStatus(selected.item).toUpperCase()}</div>
                </div>
                <Field label="Jacking force (kip)">
                  <input data-testid="strand-jacking" type="number" step="0.01" value={jacking} onChange={(e) => setJacking(e.target.value)} className={inputClass} />
                </Field>
                <Field label="Measured elongation (in)">
                  <input data-testid="strand-measured" type="number" step="0.001" value={measured} onChange={(e) => setMeasured(e.target.value)} className={inputClass} />
                </Field>
                <Field label="Notes">
                  <textarea data-testid="strand-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} className={`${inputClass} py-2`} />
                </Field>
                <button
                  type="button"
                  data-testid="strand-save"
                  onClick={() => saveStrand(false)}
                  disabled={gated || busy === "strand"}
                  className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black disabled:opacity-60"
                >
                  {busy === "strand" ? "Saving…" : "Save strand"}
                </button>
                <button
                  type="button"
                  data-testid="strand-na"
                  onClick={() => saveStrand(true)}
                  disabled={gated || busy === "strand"}
                  className="w-full min-h-12 border border-[#1C2230] font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
                >
                  Mark N/A
                </button>
                {selected.item.variance_pct != null && (
                  <div className="font-mono text-sm" style={{ color: selected.item.within_tolerance ? "#00E676" : "#FF3366" }}>
                    Δ {selected.item.variance_pct > 0 ? "+" : ""}{selected.item.variance_pct}% · {selected.item.within_tolerance ? "PASS" : "FAIL"}
                  </div>
                )}
              </div>
            )}
            {selected?.kind === "hold_down" && (
              <div className="space-y-4">
                <h3 className="font-display font-bold uppercase tracking-wider text-lg" style={{ color: holdDownColor(selected.item) }}>
                  Hold-down
                </h3>
                <div className="text-[11px] font-mono text-muted-foreground space-y-1">
                  <div>{selected.item.type_spec}</div>
                  <div>STATION {selected.item.station_from_marked_end}' FROM ME</div>
                  <div>HEIGHT {selected.item.height}" SOFFIT · QTY {selected.item.quantity_at_station} · {selected.item.orientation}</div>
                  {selected.item.verified_by ? <div>VERIFIED {selected.item.verified_by}</div> : null}
                </div>
                <Field label="Status">
                  <select data-testid="hd-status" value={hdStatus} onChange={(e) => setHdStatus(e.target.value)} className={inputClass}>
                    {HD_STATES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Notes">
                  <textarea data-testid="hd-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} className={`${inputClass} py-2`} />
                </Field>
                <button
                  type="button"
                  data-testid="hd-save"
                  onClick={saveHoldDown}
                  disabled={gated || busy === "hold"}
                  className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black disabled:opacity-60"
                >
                  {busy === "hold" ? "Saving…" : "Save hold-down"}
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 max-w-5xl">
          <div className={`${cardClass} p-5 sm:p-8`}>
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-6 flex items-center gap-2">
              <Calculator className="w-5 h-5 text-primary" /> Bed elongation report
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
                disabled={gated || busy === "save"}
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
      </div>
      )}
    </Layout>
  );
}
