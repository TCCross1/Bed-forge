import React from "react";
import { API } from "../lib/api";
import { useCompany } from "../context/CompanyContext";

export default function QrLabelPrint({ rows = [] }) {
  const company = useCompany();
  const header = company.tag_header || company.company_name || "PRESTRESS SERVICES INDUSTRIES LLC";

  if (!rows.length) {
    return (
      <div className="qr-label-empty p-8 text-center text-muted-foreground" data-testid="qr-label-empty">
        Select a pour or job to generate QR labels.
      </div>
    );
  }

  return (
    <div className="qr-label-sheet" data-testid="qr-label-sheet">
      {rows.map((row) => (
        <article key={row.id || row.qr_token} className="qr-label" data-testid={`qr-label-${row.mark}`}>
          <div className="qr-label-head">
            {company.logoSrc ? (
              <img src={company.logoSrc} alt={header} className="qr-label-logo" />
            ) : (
              <div className="qr-label-company">{header}</div>
            )}
            {company.logoSrc ? <div className="qr-label-company">{header}</div> : null}
          </div>
          <div className="qr-label-body">
            <div>
              {row.job_number ? (
                <div className="qr-label-row">
                  <span className="qr-label-kicker">JOB #</span>
                  <span className="qr-label-job">{row.job_number}</span>
                </div>
              ) : null}
              <div className="qr-label-row">
                <span className="qr-label-kicker">BEAM</span>
                <span className="qr-label-beam">{row.mark || "—"}</span>
              </div>
              <div className="qr-label-hint">Scan for specs · drawings · twin · QC</div>
            </div>
            {row.qr_token ? (
              <img
                src={`${API}/public/beams/${row.qr_token}/qr.png`}
                alt={`QR ${row.mark}`}
                className="qr-label-code"
              />
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
