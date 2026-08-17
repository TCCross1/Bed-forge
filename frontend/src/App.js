import React, { useState } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { DeviceProvider } from "./context/DeviceContext";
import { SyncProvider } from "./context/SyncContext";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import DigitalTwin from "./pages/DigitalTwin";
import NewInspection from "./pages/NewInspection";
import TensionCalculator from "./pages/TensionCalculator";
import CamberSheet from "./pages/CamberSheet";
import FinishSheet from "./pages/FinishSheet";
import PreDelivery from "./pages/PreDelivery";
import FormsExport from "./pages/FormsExport";
import Drawings from "./pages/Drawings";
import BedPlanner from "./pages/BedPlanner";
import StrandRolls from "./pages/StrandRolls";
import CylinderTags from "./pages/CylinderTags";
import ARMeasure from "./pages/ARMeasure";
import BeamDossier from "./pages/BeamDossier";
import QrLabels from "./pages/QrLabels";
import ScanBeam from "./pages/ScanBeam";
import Tutorial from "./pages/Tutorial";
import FreshTest from "./pages/FreshTest";
import BatchPlant from "./pages/BatchPlant";
import NCRDesk from "./pages/NCR";
import CommandCenter from "./pages/CommandCenter";
import OwnerPackages from "./pages/OwnerPackages";
import Finance from "./pages/Finance";
import { CompanyProvider } from "./context/CompanyContext";
import { formatApiErrorDetail } from "./lib/api";

function safeNextPath(search = "") {
  const next = new URLSearchParams(search).get("next") || "/";
  return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function Protected({ children }) {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0A0C10]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) {
    const next = `${location.pathname}${location.search || ""}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return children;
}

function LoginOrHome() {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (ready && user) return <Navigate to={safeNextPath(location.search)} replace />;
  return <Login />;
}

function PasswordGate({ children }) {
  const { user, changePassword } = useAuth();
  const location = useLocation();
  const [current, setCurrent] = useState("");
  const [nextPw, setNextPw] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!user?.must_change_password || location.pathname === "/guide") return children;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await changePassword(current, nextPw);
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || "Could not change password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0C10] grain flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-md bg-[#0F1218] border border-[#1C2230] p-6 space-y-4">
        <h1 className="font-display font-extrabold text-2xl uppercase">Set your own password</h1>
        <p className="text-sm text-muted-foreground">No standing shared passwords. Choose at least 10 characters.</p>
        <input type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="Current password" className="w-full min-h-12 bg-[#0A0C10] border border-[#1C2230] px-4 font-mono" />
        <input type="password" required minLength={10} value={nextPw} onChange={(e) => setNextPw(e.target.value)} placeholder="New password" className="w-full min-h-12 bg-[#0A0C10] border border-[#1C2230] px-4 font-mono" />
        {error && <div className="text-destructive text-sm">{error}</div>}
        <button type="submit" disabled={busy} className="w-full min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest">Save password</button>
      </form>
    </div>
  );
}

function AppRoutes() {
  return (
    <PasswordGate>
    <Routes>
      <Route path="/b/:token" element={<BeamDossier />} />
      <Route path="/guide" element={<Tutorial />} />
      <Route path="/login" element={<LoginOrHome />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/planner" element={<Protected><BedPlanner /></Protected>} />
      <Route path="/twin" element={<Protected><DigitalTwin /></Protected>} />
      <Route path="/drawings" element={<Protected><Drawings /></Protected>} />
      <Route path="/inspection" element={<Protected><NewInspection /></Protected>} />
      <Route path="/fresh" element={<Protected><FreshTest /></Protected>} />
      <Route path="/batch" element={<Protected><BatchPlant /></Protected>} />
      <Route path="/ncr" element={<Protected><NCRDesk /></Protected>} />
      <Route path="/tension" element={<Protected><TensionCalculator /></Protected>} />
      <Route path="/camber" element={<Protected><CamberSheet /></Protected>} />
      <Route path="/finish" element={<Protected><FinishSheet /></Protected>} />
      <Route path="/release" element={<Protected><PreDelivery /></Protected>} />
      <Route path="/forms" element={<Protected><FormsExport /></Protected>} />
      <Route path="/rolls" element={<Protected><StrandRolls /></Protected>} />
      <Route path="/tags" element={<Protected><CylinderTags /></Protected>} />
      <Route path="/qr" element={<Protected><QrLabels /></Protected>} />
      <Route path="/scan" element={<Protected><ScanBeam /></Protected>} />
      <Route path="/measure" element={<Protected><ARMeasure /></Protected>} />
      <Route path="/command" element={<Protected><CommandCenter /></Protected>} />
      <Route path="/packages" element={<Protected><OwnerPackages /></Protected>} />
      <Route path="/finance" element={<Protected><Finance /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </PasswordGate>
  );
}

function App() {
  return (
    <div className="App">
      <DeviceProvider>
        <CompanyProvider>
        <AuthProvider>
          <BrowserRouter>
            <SyncProvider>
              <AppRoutes />
            </SyncProvider>
          </BrowserRouter>
          <Toaster theme="dark" position="top-right" richColors />
        </AuthProvider>
        </CompanyProvider>
      </DeviceProvider>
    </div>
  );
}

export default App;
