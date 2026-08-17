import React, { useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import {
  LayoutGrid,
  Box,
  ClipboardCheck,
  Calculator,
  FileSpreadsheet,
  LogOut,
  Ruler,
  Sparkles,
  Truck,
  Menu,
  X,
  Upload,
  CalendarDays,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { ROLE_LABELS } from "../lib/constants";

export const MARK_SRC = "/brand/bedforge-mark.png";
export const LOCKUP_SRC = "/brand/bedforge-lockup.png";

export function BrandMark({ className = "h-10 w-auto", testid = "brand-mark" }) {
  return (
    <img
      src={MARK_SRC}
      alt="BedForge"
      data-testid={testid}
      className={`object-contain select-none pointer-events-none ${className}`}
      draggable={false}
    />
  );
}

export function BrandLockup({ className = "h-12 w-auto", testid = "brand-lockup" }) {
  return (
    <img
      src={LOCKUP_SRC}
      alt="BedForge Quality Control — Precision. Strength. Quality."
      data-testid={testid}
      className={`object-contain select-none pointer-events-none ${className}`}
      draggable={false}
    />
  );
}

const PRIMARY_NAV = [
  { to: "/", label: "Board", icon: LayoutGrid, testid: "nav-dashboard" },
  { to: "/twin", label: "Twin", icon: Box, testid: "nav-twin" },
  { to: "/inspection", label: "Inspect", icon: ClipboardCheck, testid: "nav-inspection" },
  { to: "/tension", label: "Tension", icon: Calculator, testid: "nav-tension" },
  { to: "/forms", label: "Forms", icon: FileSpreadsheet, testid: "nav-forms" },
];

const SECONDARY_NAV = [
  { to: "/planner", label: "Planner", icon: CalendarDays, testid: "nav-planner" },
  { to: "/drawings", label: "Drawings", icon: Upload, testid: "nav-drawings" },
  { to: "/camber", label: "Camber", icon: Ruler, testid: "nav-camber" },
  { to: "/finish", label: "Finish", icon: Sparkles, testid: "nav-finish" },
  { to: "/release", label: "Release", icon: Truck, testid: "nav-release" },
];

function linkClass(isActive) {
  return `flex items-center gap-3 px-4 min-h-12 rounded-none font-medium tracking-wide transition-colors duration-100 ${
    isActive
      ? "bg-primary text-white"
      : "text-muted-foreground hover:bg-secondary hover:text-white"
  }`;
}

function NavItems({ items, onNavigate, endHome }) {
  return items.map((item) => {
    const Icon = item.icon;
    return (
      <NavLink
        key={item.to}
        to={item.to}
        end={endHome && item.to === "/"}
        data-testid={item.testid}
        onClick={onNavigate}
        className={({ isActive }) => linkClass(isActive)}
      >
        <Icon className="w-5 h-5 shrink-0" />
        <span className="font-condensed text-base uppercase tracking-wider">{item.label}</span>
      </NavLink>
    );
  });
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);

  const signOut = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex bg-[#0A0C10] grain">
      <aside
        className="hidden lg:flex w-64 shrink-0 border-r border-[#1C2230] bg-[#0C0E13] flex-col fixed h-screen z-20"
        data-testid="desktop-sidebar"
      >
        <div className="h-24 flex items-center justify-start px-4 border-b border-[#1C2230]">
          <NavLink to="/" className="flex items-center" aria-label="BedForge home">
            <BrandMark className="h-16 w-auto" testid="sidebar-brand-mark" />
          </NavLink>
        </div>

        <nav className="flex-1 py-4 flex flex-col gap-1 px-3 overflow-y-auto">
          <div className="px-4 pb-2 text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground">Primary</div>
          <NavItems items={PRIMARY_NAV} endHome />
          <div className="px-4 pt-5 pb-2 text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground">Secondary</div>
          <NavItems items={SECONDARY_NAV} />
        </nav>

        <div className="border-t border-[#1C2230] p-4">
          <div className="mb-3">
            <div className="text-sm font-semibold truncate" data-testid="current-user-name">{user?.name}</div>
            <div className="text-xs text-primary font-mono uppercase tracking-wider">
              {ROLE_LABELS[user?.role] || user?.role}
            </div>
          </div>
          <button
            data-testid="logout-btn"
            onClick={signOut}
            className="w-full min-h-12 flex items-center justify-center gap-2 border border-[#1C2230] rounded-none text-sm font-semibold uppercase tracking-wider hover:bg-destructive hover:border-destructive hover:text-white transition-colors duration-100"
          >
            <LogOut className="w-4 h-4" /> Sign Out
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 lg:ml-64">
        <header
          className="lg:hidden sticky top-0 z-30 h-14 border-b border-[#1C2230] bg-[#0A0C10]/95 backdrop-blur grid grid-cols-[auto_1fr_auto] items-center px-3"
          data-testid="mobile-topbar"
        >
          <NavLink to="/" className="flex items-center min-h-12 justify-self-start" aria-label="BedForge home">
            <BrandMark className="h-10 w-auto" testid="mobile-brand-mark" />
          </NavLink>
          <div className="flex items-center justify-center min-w-0 px-2">
            <BrandLockup className="h-9 w-auto max-w-full" testid="mobile-brand-lockup" />
          </div>
          <button
            data-testid="mobile-more-btn"
            onClick={() => setMoreOpen(true)}
            className="min-h-12 min-w-12 flex items-center justify-center border border-[#1C2230] rounded-none justify-self-end"
            aria-label="Open secondary navigation"
          >
            <Menu className="w-5 h-5" />
          </button>
        </header>

        {moreOpen && (
          <div className="lg:hidden fixed inset-0 z-40" data-testid="mobile-more-sheet">
            <button className="absolute inset-0 bg-black/70" onClick={() => setMoreOpen(false)} aria-label="Close menu" />
            <div className="absolute bottom-0 left-0 right-0 bg-[#0F1218] border-t border-[#1C2230] p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <BrandMark className="h-10 w-auto" testid="sheet-brand-mark" />
                  <div>
                    <div className="font-display font-bold uppercase tracking-wider">More</div>
                    <div className="text-xs text-muted-foreground font-mono">{user?.name} · {ROLE_LABELS[user?.role] || user?.role}</div>
                  </div>
                </div>
                <button onClick={() => setMoreOpen(false)} className="min-h-12 min-w-12 flex items-center justify-center border border-[#1C2230] rounded-none">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="grid grid-cols-1 gap-1 mb-3">
                <NavItems items={SECONDARY_NAV} onNavigate={() => setMoreOpen(false)} />
              </div>
              <button
                onClick={() => { setMoreOpen(false); signOut(); }}
                className="w-full min-h-12 flex items-center justify-center gap-2 border border-[#1C2230] rounded-none text-sm font-semibold uppercase tracking-wider hover:bg-destructive hover:border-destructive hover:text-white"
              >
                <LogOut className="w-4 h-4" /> Sign Out
              </button>
            </div>
          </div>
        )}

        <main className="flex-1 relative z-10 pb-24 lg:pb-0">{children}</main>
      </div>

      <nav
        className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-[#1C2230] bg-[#0C0E13]/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
        data-testid="mobile-bottom-nav"
      >
        <div className="grid grid-cols-5">
          {PRIMARY_NAV.map((item) => {
            const Icon = item.icon;
            const active = item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                data-testid={`${item.testid}-mobile`}
                className={`flex flex-col items-center justify-center min-h-14 gap-0.5 transition-colors duration-100 ${
                  active ? "text-primary" : "text-muted-foreground"
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="font-condensed text-[10px] uppercase tracking-wider">{item.label}</span>
              </NavLink>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export function PageHeader({ title, subtitle, right }) {
  return (
    <div className="sticky top-14 lg:top-0 z-10 bg-[#0A0C10]/95 backdrop-blur border-b border-[#1C2230]">
      <div className="hidden lg:flex h-24 items-center justify-center px-8" data-testid="hero-header-banner">
        <BrandLockup className="h-16 w-auto max-w-full" testid="header-brand-lockup" />
      </div>
      <div className="min-h-16 lg:border-t lg:border-[#1C2230] flex items-center justify-between gap-3 px-4 sm:px-6 lg:px-8 py-3">
        <div className="min-w-0">
          <h1 className="font-display font-extrabold text-xl sm:text-2xl lg:text-3xl uppercase tracking-tight leading-none truncate">{title}</h1>
          {subtitle && <p className="text-xs sm:text-sm text-muted-foreground mt-1 truncate">{subtitle}</p>}
        </div>
        {right}
      </div>
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <div>
      <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

export const inputClass =
  "w-full bg-[#0A0C10] border border-[#1C2230] rounded-none px-4 min-h-12 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary";

export const cardClass = "bg-[#0F1218] border border-[#1C2230] rounded-none";
