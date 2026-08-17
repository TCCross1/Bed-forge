import React from "react";
import { useCompany } from "../context/CompanyContext";
import { BEAMS_PER_LABEL } from "../lib/cylinderTags";

export default function CylinderPrint({ rows, runDate }) {
  const company = useCompany();
  const header = company.tag_header || company.company_name || "PRESTRESS SERVICES INDUSTRIES LLC";

  if (!rows?.length) {
    return (
      <div className="cylinder-print-empty p-8 text-center text-muted-foreground" data-testid="cylinder-print-empty">
        No tags are ready to print.
      </div>
    );
  }

  return (
    <div className="cylinder-print-sheet" data-testid="cylinder-print-sheet">
      {rows.map((row) => {
        const beams = [];
        for (let i = 1; i <= BEAMS_PER_LABEL; i += 1) {
          const mark = String(row[`beam_${i}`] || "").trim();
          if (mark) beams.push(mark);
        }
        return (
          <article key={`${row.label_number}-${row.job_slot}-${row.cylinder_copy}-${row.part}`} className="cylinder-tag" data-testid={`cylinder-tag-${row.label_number}`}>
            <header className="cylinder-tag-head">
              {company.logoSrc ? (
                <img src={company.logoSrc} alt={header} className="cylinder-tag-logo" />
              ) : null}
              <div className="cylinder-tag-company">{header}</div>
            </header>
            <div className="cylinder-tag-row">
              {row.job_number ? <div className="cylinder-tag-job">JOB # {row.job_number}</div> : null}
              {row.pour_number ? <div className="cylinder-tag-pour">POUR # {row.pour_number}</div> : null}
            </div>
            {beams.length > 0 && (
              <div className="cylinder-tag-beams">
                <div className="cylinder-tag-kicker">BEAMS</div>
                <div className="cylinder-tag-beam-list">{beams.join("  ·  ")}</div>
              </div>
            )}
            <footer className="cylinder-tag-foot">
              <div>
                {row.qc_tech ? <span>QC {row.qc_tech}</span> : null}
                {row.qc_tech && row.date ? <span className="cylinder-tag-sep"> | </span> : null}
                {row.date ? <span>{row.date}</span> : null}
              </div>
              <div className="cylinder-tag-meta">
                {Number(row.copies_total) > 1 ? <span>CYL {row.cylinder_copy} OF {row.copies_total}</span> : null}
                {row.part_caption ? <span>{row.part_caption}</span> : null}
              </div>
            </footer>
          </article>
        );
      })}
      {runDate ? <div className="cylinder-print-run">Run {runDate} · {rows.length} physical labels · print at 100% / Actual Size</div> : null}
    </div>
  );
}
