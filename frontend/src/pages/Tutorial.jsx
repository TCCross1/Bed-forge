import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BookOpen, ChevronDown, Search, Shield } from "lucide-react";
import Layout, { PageHeader, cardClass } from "../components/Layout";
import { searchTutorial, TUTORIAL_SECTIONS, tutorialSectionById } from "../lib/tutorial";
import { useAuth } from "../context/AuthContext";

export default function Tutorial({ embedded = false }) {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const wanted = params.get("section") || TUTORIAL_SECTIONS[0].id;
  const [open, setOpen] = useState(wanted);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const next = params.get("section");
    if (next && tutorialSectionById(next)) setOpen(next);
  }, [params]);

  useEffect(() => {
    if (!open) return undefined;
    const node = document.getElementById(`tutorial-${open}`);
    if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [open]);

  const sections = useMemo(() => searchTutorial(query), [query]);

  const select = (id) => {
    const next = open === id ? "" : id;
    setOpen(next);
    const copy = new URLSearchParams(params);
    if (next) copy.set("section", next);
    else copy.delete("section");
    setParams(copy, { replace: true });
  };

  const inner = (
    <div className="p-4 sm:p-6 lg:p-8 max-w-4xl space-y-3" data-testid="master-tutorial">
      <div className={`${cardClass} p-5 sm:p-6 border-l-2`} style={{ borderLeftColor: "#C9A227" }}>
        <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">For everyone on the plant</div>
        <h2 className="font-display font-extrabold text-2xl uppercase tracking-tight mt-1">How BedForge works — for dummies</h2>
        <p className="text-sm text-muted-foreground mt-2">
          Written for someone who has never used the system. Organized by the real day, not the menus. This copy lives on the phone — you can read it with no signal.
        </p>
        <label className="mt-4 flex items-center gap-2 min-h-12 border border-[#1C2230] bg-[#0A0C10] px-3">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            data-testid="tutorial-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search: heat number, camber, override…"
            className="flex-1 bg-transparent min-h-12 text-sm focus:outline-none"
          />
        </label>
      </div>

      {sections.length === 0 && (
        <div className={`${cardClass} p-5 text-sm text-muted-foreground`}>No section matches that search. Try “tension”, “heat”, or “QR”.</div>
      )}

      {sections.map((section) => {
        const active = open === section.id;
        return (
          <section key={section.id} id={`tutorial-${section.id}`} className={`${cardClass} overflow-hidden scroll-mt-28`}>
            <button
              type="button"
              onClick={() => select(section.id)}
              className="w-full min-h-14 px-4 sm:px-5 flex items-center justify-between gap-3 text-left"
              data-testid={`tutorial-${section.id}`}
              aria-expanded={active}
            >
              <span className="font-display font-bold uppercase tracking-wide">{section.title}</span>
              <ChevronDown className={`w-5 h-5 shrink-0 transition-transform ${active ? "rotate-180" : ""}`} />
            </button>
            {active && (
              <div className="px-4 sm:px-5 pb-5 space-y-3 border-t border-[#1C2230] pt-4">
                {section.why && (
                  <div className="border border-[#C9A227]/40 bg-[#C9A227]/10 px-3 py-3" data-testid={`tutorial-why-${section.id}`}>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-[#C9A227]">Why this matters</div>
                    <p className="text-sm leading-relaxed mt-1">{section.why}</p>
                  </div>
                )}
                {section.body.map((para) => (
                  <p key={para.slice(0, 48)} className="text-sm leading-relaxed text-[#D5D9E2]">{para}</p>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );

  if (embedded || !user) {
    return (
      <div className="min-h-screen bg-[#0A0C10] grain">
        <header className="sticky top-0 z-20 border-b border-[#1C2230] bg-[#0A0C10]/95 backdrop-blur">
          <div className="max-w-4xl mx-auto px-4 min-h-16 flex items-center justify-between">
            <div className="flex items-center gap-2 font-display font-extrabold uppercase tracking-tight">
              <BookOpen className="w-5 h-5 text-primary" /> How BedForge works
            </div>
            <Link to={user ? "/" : "/login"} className="min-h-12 px-4 border border-[#1C2230] font-semibold uppercase tracking-wider text-xs hover:border-primary hover:text-primary flex items-center">
              {user ? "Plant" : "Sign in"}
            </Link>
          </div>
        </header>
        {inner}
      </div>
    );
  }

  return (
    <Layout>
      <PageHeader
        title="Master tutorial"
        subtitle="For dummies — the real day on the plant, why each lock exists, and what to do when it goes wrong"
        right={
          <Link to="/command" className="min-h-12 px-4 border border-[#1C2230] flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary">
            <Shield className="w-4 h-4" /> Command
          </Link>
        }
      />
      {inner}
    </Layout>
  );
}
