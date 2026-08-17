import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LayoutGrid, Box, ClipboardCheck, Calculator, FileSpreadsheet, LogOut, HardHat } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { ROLE_LABELS } from "../lib/constants";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutGrid, testid: "nav-dashboard" },
  { to: "/twin", label: "Digital Twin", icon: Box, testid: "nav-twin" },
  { to: "/inspection", label: "New Inspection", icon: ClipboardCheck, testid: "nav-inspection" },
  { to: "/tension", label: "Tension Calc", icon: Calculator, testid: "nav-tension" },
  { to: "/forms", label: "Forms Export", icon: FileSpreadsheet, testid: "nav-forms" },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex bg-background grain">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-border bg-[#0C0E13] flex flex-col fixed h-screen z-20">
        <div className="h-20 flex items-center gap-3 px-6 border-b border-border">
          <div className="w-10 h-10 bg-primary flex items-center justify-center rounded-sm">
            <HardHat className="w-6 h-6 text-white" />
          </div>
          <div>
            <div className="font-display font-extrabold text-lg leading-none tracking-tight">BEDFORGE</div>
            <div className="text-[10px] tracking-[0.3em] text-muted-foreground font-mono">QC · PSI LLC</div>
          </div>
        </div>

        <nav className="flex-1 py-4 flex flex-col gap-1 px-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                data-testid={item.testid}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 min-h-12 rounded-sm font-medium tracking-wide transition-colors duration-100 ${
                    isActive
                      ? "bg-primary text-white"
                      : "text-muted-foreground hover:bg-secondary hover:text-white"
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                <span className="font-condensed text-base uppercase tracking-wider">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-border p-4">
          <div className="mb-3">
            <div className="text-sm font-semibold truncate" data-testid="current-user-name">{user?.name}</div>
            <div className="text-xs text-primary font-mono uppercase tracking-wider">{ROLE_LABELS[user?.role] || user?.role}</div>
          </div>
          <button
            data-testid="logout-btn"
            onClick={() => { logout(); navigate("/login"); }}
            className="w-full min-h-12 flex items-center justify-center gap-2 border border-border rounded-sm text-sm font-semibold uppercase tracking-wider hover:bg-destructive hover:border-destructive hover:text-white transition-colors duration-100"
          >
            <LogOut className="w-4 h-4" /> Sign Out
          </button>
        </div>
      </aside>

      <main className="flex-1 ml-64 relative z-10">{children}</main>
    </div>
  );
}

export function PageHeader({ title, subtitle, right }) {
  return (
    <div className="h-20 border-b border-border flex items-center justify-between px-8 sticky top-0 bg-background/95 backdrop-blur z-10">
      <div>
        <h1 className="font-display font-extrabold text-2xl sm:text-3xl uppercase tracking-tight leading-none">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
