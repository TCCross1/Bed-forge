import React, { useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, ChevronDown, Shield } from "lucide-react";
import Layout, { PageHeader, cardClass } from "../components/Layout";
import { TUTORIAL_SECTIONS } from "../lib/tutorial";
import { useAuth } from "../context/AuthContext";

export default function Tutorial({ embedded = false }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(TUTORIAL_SECTIONS[0].id);
  const inner = (
    <div className="p-4 sm:p-6 lg:p-8 max-w-4xl space-y-3" data-testid="master-tutorial">
      <div className={`${cardClass} p-5 sm:p-6 border-l-2`} style={{ borderLeftColor: "#C9A227" }}>
        <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">For everyone on the plant</div>
        <h2 className="font-display font-extrabold text-2xl uppercase tracking-tight mt-1">Master tutorial</h2>
        <p className="text-sm text-muted-foreground mt-2">
          Plain language. No jargon test. This is how BedForge works, who can do what, and why it is built like a plant that has already been attacked.
        </p>
      </div>
      {TUTORIAL_SECTIONS.map((section) => {
        const active = open === section.id;
        return (
          <section key={section.id} className={`${cardClass} overflow-hidden`}>
            <button
              type="button"
              onClick={() => setOpen(active ? "" : section.id)}
              className="w-full min-h-14 px-4 sm:px-5 flex items-center justify-between gap-3 text-left"
              data-testid={`tutorial-${section.id}`}
            >
              <span className="font-display font-bold uppercase tracking-wide">{section.title}</span>
              <ChevronDown className={`w-5 h-5 shrink-0 transition-transform ${active ? "rotate-180" : ""}`} />
            </button>
            {active && (
              <div className="px-4 sm:px-5 pb-5 space-y-3 border-t border-[#1C2230] pt-4">
                {section.body.map((para) => (
                  <p key={para.slice(0, 24)} className="text-sm leading-relaxed text-[#D5D9E2]">{para}</p>
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
        subtitle="For dummies — how the plant runs, who holds the keys, and why it is locked down"
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
