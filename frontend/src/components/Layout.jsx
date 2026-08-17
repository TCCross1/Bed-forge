import React, { useState } from "react";
import { Link, NavLink, useNavigate, useLocation } from "react-router-dom";
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
  ScanLine,
  ScanBarcode,
  Tags,
  QrCode,
  BookOpen,
  Shield,
  Package,
  DollarSign,
  FlaskConical,
  Factory,
  AlertTriangle,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useDevice } from "../context/DeviceContext";
import { useCompany } from "../context/CompanyContext";
import { ROLE_LABELS, isExec } from "../lib/constants";
import OfflineBanner from "./OfflineBanner";
import ForgeCoach from "./ForgeCoach";

export const MARK_SRC = "/brand/bedforge-mark.png";
export const LOCKUP_SRC = "/brand/bedforge-lockup.png";

export function BrandMark({ className = "h-10 w-auto", testid = "brand-mark" }) {
  const company = useCompany();
  const src = company?.logoSrc || MARK_SRC;
  const alt = company?.company_name || "BedForge";
  return (
    <img
      src={src}
      alt={alt}
      data-testid={testid}
      className={`object-contain select-none pointer-events-none ${className}`}
      draggable={false}
    />
  );
}

export function BrandLockup({ className = "h-12 w-auto", testid = "brand-lockup" }) {
  const company = useCompany();
  const src = company?.logoSrc || LOCKUP_SRC;
  const alt = company?.app_name || "BedForge Quality Control — Precision. Strength. Quality.";
  return (
    <img
      src={src}
      alt={alt}
      data-testid={testid}
      className={`object-contain select-none pointer-events-none ${className}`}
      draggable={false}
    />
  );
}

const PRIMARY_NAV = [
  { to: "/", label: "Board", icon: LayoutGrid, testid: "nav-dashboard" },
  { to: "/twin", label: "Twin", icon: Box, testid: "nav-twin" },
  { to: "/rolls", label: "Rolls", icon: ScanBarcode, testid: "nav-rolls" },
  { to: "/fresh", label: "Fresh Test", icon: FlaskConical, testid: "nav-fresh", accent: true },
  { to: "/batch", label: "Batch Plant", icon: Factory, testid: "nav-batch" },
  { to: "/inspection", label: "Inspect", icon: ClipboardCheck, testid: "nav-inspection" },
  { to: "/tags", label: "Tags", icon: Tags, testid: "nav-tags" },
  { to: "/tension", label: "Tension", icon: Calculator, testid: "nav-tension" },
  { to: "/forms", label: "Forms", icon: FileSpreadsheet, testid: "nav-forms" },
  { to: "/packages", label: "Packages", icon: Package, testid: "nav-packages" },
];

const FIELD_NAV = [
  { to: "/", label: "Board", icon: LayoutGrid, testid: "nav-dashboard" },
  { to: "/rolls", label: "Rolls", icon: ScanBarcode, testid: "nav-rolls" },
  { to: "/fresh", label: "Fresh", icon: FlaskConical, testid: "nav-fresh", accent: true },
  { to: "/twin", label: "Twin", icon: Box, testid: "nav-twin" },
  { to: "/tension", label: "Tension", icon: Calculator, testid: "nav-tension" },
];

const SECONDARY_NAV = [
  { to: "/ncr", label: "NCR", icon: AlertTriangle, testid: "nav-ncr" },
  { to: "/planner", label: "Planner", icon: CalendarDays, testid: "nav-planner" },
  { to: "/drawings", label: "Drawings", icon: Upload, testid: "nav-drawings" },
  { to: "/camber", label: "Camber", icon: Ruler, testid: "nav-camber" },
  { to: "/finish", label: "Finish", icon: Sparkles, testid: "nav-finish" },
  { to: "/release", label: "Release", icon: Truck, testid: "nav-release" },
  { to: "/measure", label: "Digital Tape", icon: ScanLine, testid: "nav-measure" },
  { to: "/scan", label: "Scan QR", icon: ScanLine, testid: "nav-scan" },
  { to: "/qr", label: "QR Labels", icon: QrCode, testid: "nav-qr" },
  { to: "/guide", label: "Tutorial", icon: BookOpen, testid: "nav-guide" },
];

const COMMAND_SECONDARY = [
  { to: "/ncr", label: "NCR", icon: AlertTriangle, testid: "nav-ncr" },
  { to: "/planner", label: "Planner", icon: CalendarDays, testid: "nav-planner" },
  { to: "/drawings", label: "Drawings", icon: Upload, testid: "nav-drawings" },
  { to: "/camber", label: "Camber", icon: Ruler, testid: "nav-camber" },
  { to: "/finish", label: "Finish", icon: Sparkles, testid: "nav-finish" },
  { to: "/release", label: "Release", icon: Truck, testid: "nav-release" },
  { to: "/measure", label: "Tape Review", icon: ScanLine, testid: "nav-measure" },
  { to: "/scan", label: "Scan QR", icon: ScanLine, testid: "nav-scan" },
  { to: "/qr", label: "QR Labels", icon: QrCode, testid: "nav-qr" },
  { to: "/guide", label: "Tutorial", icon: BookOpen, testid: "nav-guide" },
];

function linkClass(isActive, accent) {
  if (isActive) {
    return "flex items-center gap-3 px-4 min-h-12 rounded-none font-medium tracking-wide transition-colors duration-100 bg-primary text-white";
  }
  if (accent) {
    return "flex items-center gap-3 px-4 min-h-12 rounded-none font-medium tracking-wide transition-colors duration-100 text-[#C9A227] border border-[#C9A227]/40 hover:bg-[#C9A227]/10 hover:text-[#C9A227]";
  }
  return "flex items-center gap-3 px-4 min-h-12 rounded-none font-medium tracking-wide transition-colors duration-100 text-muted-foreground hover:bg-secondary hover:text-white";
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
        className={({ isActive }) => linkClass(isActive, item.accent || item.to === "/fresh")}
      >
        <Icon className="w-5 h-5 shrink-0" />
        <span className="font-condensed text-base uppercase tracking-wider">{item.label}</span>
      </NavLink>
    );
  });
}

export function ARMeasureLink({ beamId, purpose = "tape", compact = false }) {
  const qs = new URLSearchParams();
  if (beamId) qs.set("beam", beamId);
  if (purpose) qs.set("purpose", purpose);
  return (
    <Link
      to={`/measure?${qs.toString()}`}
      data-testid="ar-measure-entry"
      title="Digital tape — daily calibration, not the Fresh Test tab"
      className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
    >
      <ScanLine className="w-4 h-4" /> {compact ? "Tape" : "Digital Tape"}
    </Link>
  );
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const device = useDevice();
  const navigate = useNavigate();
  const location = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const command = device.command;
  const field = device.field;
  const secondary = [
    ...(command ? COMMAND_SECONDARY : SECONDARY_NAV),
    ...(isExec(user?.role) ? [
      { to: "/finance", label: "Dollars", icon: DollarSign, testid: "nav-finance" },
      { to: "/command", label: "Command", icon: Shield, testid: "nav-command" },
    ] : []),
  ];
  const fieldMore = [
    { to: "/fresh", label: "Fresh Test — Spread / Slump", icon: FlaskConical, testid: "nav-fresh-more" },
    { to: "/ncr", label: "NCR — file / close", icon: AlertTriangle, testid: "nav-ncr-more" },
    { to: "/batch", label: "Batch Plant", icon: Factory, testid: "nav-batch-more" },
    { to: "/guide", label: "Tutorial", icon: BookOpen, testid: "nav-guide" },
    ...(isExec(user?.role) ? [
      { to: "/finance", label: "Dollars", icon: DollarSign, testid: "nav-finance" },
      { to: "/command", label: "Command", icon: Shield, testid: "nav-command" },
    ] : []),
    { to: "/scan", label: "Scan QR", icon: ScanLine, testid: "nav-scan" },
    { to: "/qr", label: "QR Labels", icon: QrCode, testid: "nav-qr" },
    { to: "/inspection", label: "Inspect", icon: ClipboardCheck, testid: "nav-inspection" },
    { to: "/tags", label: "Tags", icon: Tags, testid: "nav-tags" },
    { to: "/forms", label: "Forms", icon: FileSpreadsheet, testid: "nav-forms" },
    { to: "/packages", label: "Packages", icon: Package, testid: "nav-packages" },
    { to: "/measure", label: "Digital Tape", icon: ScanLine, testid: "nav-measure" },
    ...SECONDARY_NAV.filter((i) => !["/measure", "/scan", "/qr", "/guide", "/ncr"].includes(i.to)),
  ];

  const signOut = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className={`min-h-screen flex bg-[#0A0C10] grain ${field ? "bf-field" : "bf-command"}`} data-device={field ? "field" : "command"}>
      <aside
        className={`${command ? "flex" : "hidden"} w-64 shrink-0 border-r border-[#1C2230] bg-[#0C0E13] flex-col fixed h-screen z-20`}
        data-testid="desktop-sidebar"
      >
        <div className="h-24 flex items-center justify-start px-4 border-b border-[#1C2230]">
          <NavLink to="/" className="flex items-center" aria-label="BedForge home">
            <BrandMark className="h-16 w-auto" testid="sidebar-brand-mark" />
          </NavLink>
        </div>

        <nav className="flex-1 py-4 flex flex-col gap-1 px-3 overflow-y-auto">
          <div className="px-4 pb-2 text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground">Command</div>
          <NavItems items={PRIMARY_NAV} endHome />
          <div className="px-4 pt-5 pb-2 text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground">Review &amp; release</div>
          <NavItems items={secondary} />
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

      <div className={`flex-1 flex flex-col min-w-0 ${command ? "ml-64" : ""}`}>
        <header
          className={`${field ? "grid" : "hidden"} sticky top-0 z-30 h-14 border-b border-[#1C2230] bg-[#0A0C10]/95 backdrop-blur grid-cols-[auto_1fr] items-center px-3`}
          data-testid="mobile-topbar"
        >
          <NavLink to="/" className="flex items-center min-h-12 justify-self-start" aria-label="BedForge home">
            <BrandMark className="h-10 w-auto" testid="mobile-brand-mark" />
          </NavLink>
          <div className="flex items-center justify-center min-w-0 px-2">
            <BrandLockup className="h-9 w-auto max-w-full" testid="mobile-brand-lockup" />
          </div>
        </header>

        {moreOpen && field && (
          <div className="fixed inset-0 z-40" data-testid="mobile-more-sheet">
            <button className="absolute inset-0 bg-black/70" onClick={() => setMoreOpen(false)} aria-label="Close menu" />
            <div className="absolute bottom-0 left-0 right-0 bg-[#0F1218] border-t border-[#1C2230] p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <BrandMark className="h-10 w-auto" testid="sheet-brand-mark" />
                  <div>
                    <div className="font-display font-bold uppercase tracking-wider">Field tools</div>
                    <div className="text-xs text-muted-foreground font-mono">{user?.name} · {ROLE_LABELS[user?.role] || user?.role}</div>
                  </div>
                </div>
                <button onClick={() => setMoreOpen(false)} className="min-h-12 min-w-12 flex items-center justify-center border border-[#1C2230] rounded-none">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="grid grid-cols-1 gap-1 mb-3">
                <NavItems items={fieldMore} onNavigate={() => setMoreOpen(false)} />
              </div>
              <button
                type="button"
                data-testid="forge-coach-open-sheet"
                onClick={() => { setMoreOpen(false); window.dispatchEvent(new CustomEvent("bf-coach-open")); }}
                className="w-full min-h-12 mb-2 flex items-center justify-center gap-2 border border-[#C9A227] text-[#C9A227] text-sm font-semibold uppercase tracking-wider"
              >
                Ask Expert
              </button>
              <button
                onClick={() => { setMoreOpen(false); signOut(); }}
                className="w-full min-h-14 flex items-center justify-center gap-2 border border-[#1C2230] rounded-none text-sm font-semibold uppercase tracking-wider hover:bg-destructive hover:border-destructive hover:text-white"
              >
                <LogOut className="w-4 h-4" /> Sign Out
              </button>
            </div>
          </div>
        )}

        <main className={`flex-1 relative z-10 ${field ? "pb-24" : "pb-0"}`}>
          <OfflineBanner />
          {children}
        </main>
      </div>

      <nav
        className={`${field ? "block" : "hidden"} fixed bottom-0 inset-x-0 z-30 border-t border-[#1C2230] bg-[#0C0E13]/95 backdrop-blur pb-[env(safe-area-inset-bottom)]`}
        data-testid="mobile-bottom-nav"
      >
        <div className="grid grid-cols-6">
          {FIELD_NAV.map((item) => {
            const Icon = item.icon;
            const active = item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to);
            const idleColor = item.accent ? "text-[#C9A227]" : "text-muted-foreground";
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                data-testid={`${item.testid}-mobile`}
                className={`flex flex-col items-center justify-center min-h-14 gap-0.5 transition-colors duration-100 ${
                  active ? "text-primary" : idleColor
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="font-condensed text-[10px] uppercase tracking-wider">{item.label}</span>
              </NavLink>
            );
          })}
          <button
            type="button"
            data-testid="mobile-more-btn"
            onClick={() => setMoreOpen(true)}
            className={`flex flex-col items-center justify-center min-h-14 gap-0.5 ${moreOpen ? "text-primary" : "text-muted-foreground"}`}
            aria-label="Open field tools"
          >
            <Menu className="w-5 h-5" />
            <span className="font-condensed text-[10px] uppercase tracking-wider">More</span>
          </button>
        </div>
      </nav>
      <ForgeCoach />
    </div>
  );
}

export function PageHeader({ title, subtitle, right }) {
  const device = useDevice();
  return (
    <div className={`sticky z-10 bg-[#0A0C10]/95 backdrop-blur border-b border-[#1C2230] ${device.field ? "top-14" : "top-0"}`}>
      <div className={`${device.command ? "flex" : "hidden"} h-24 items-center justify-center px-8`} data-testid="hero-header-banner">
        <BrandLockup className="h-16 w-auto max-w-full" testid="header-brand-lockup" />
      </div>
      <div className={`min-h-16 flex items-center justify-between gap-3 px-4 sm:px-6 lg:px-8 py-3 ${device.command ? "border-t border-[#1C2230]" : ""}`}>
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
