import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, cardClass } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { isExec } from "../lib/constants";
import { toast } from "sonner";
import { AlertTriangle, DollarSign, Loader2 } from "lucide-react";

function Money({ usd }) {
  const n = Number(usd) || 0;
  return <span className="font-mono">${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>;
}

export default function Finance() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isExec(user?.role)) return undefined;
    api.get("/finance/signals")
      .then((r) => setData(r.data))
      .catch((err) => {
        console.error("[finance] load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load financial signals");
      })
      .finally(() => setLoading(false));
  }, [user?.role]);

  if (!isExec(user?.role)) return <Navigate to="/" replace />;

  return (
    <Layout>
      <PageHeader
        title="Quality dollars"
        subtitle="Cost signals only — NCRs, scrap, overtime on holds, bed-days at risk. Not a general ledger."
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-5xl space-y-4">
        {loading && (
          <div className="flex items-center justify-center h-40 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading owner view…
          </div>
        )}
        {data && (
          <>
            <div className={`${cardClass} p-6`} data-testid="finance-total">
              <div className="text-[10px] font-mono uppercase tracking-widest text-[#C9A227]">At risk right now</div>
              <div className="font-display font-extrabold text-4xl mt-2" style={{ color: "#FFD600" }}>
                <DollarSign className="w-8 h-8 inline mb-1" />
                <Money usd={data.total_quality_dollars_at_risk} />
              </div>
              <p className="text-xs text-muted-foreground mt-2">{data.disclaimer}</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {(data.lines || []).map((line) => (
                <div key={line.id} className={`${cardClass} p-5`} data-testid={`finance-${line.id}`}>
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{line.label}</div>
                  <div className="font-mono text-2xl font-bold mt-2" style={{ color: line.count ? "#FFD600" : "#00E676" }}>
                    <Money usd={line.usd} />
                  </div>
                  <div className="text-xs font-mono text-muted-foreground mt-1">{line.count} open</div>
                </div>
              ))}
            </div>
            {(data.hold_marks || []).length > 0 && (
              <div className={`${cardClass} p-5`}>
                <div className="font-display font-bold uppercase tracking-wider flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-4 h-4 text-[#FFD600]" /> Holds
                </div>
                <div className="font-mono text-sm">{data.hold_marks.join(" · ")}</div>
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}
