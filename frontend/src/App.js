import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
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
import { CompanyProvider } from "./context/CompanyContext";

function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0A0C10]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  const { user, ready } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={ready && user ? <Navigate to="/" replace /> : <Login />}
      />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/planner" element={<Protected><BedPlanner /></Protected>} />
      <Route path="/twin" element={<Protected><DigitalTwin /></Protected>} />
      <Route path="/drawings" element={<Protected><Drawings /></Protected>} />
      <Route path="/inspection" element={<Protected><NewInspection /></Protected>} />
      <Route path="/tension" element={<Protected><TensionCalculator /></Protected>} />
      <Route path="/camber" element={<Protected><CamberSheet /></Protected>} />
      <Route path="/finish" element={<Protected><FinishSheet /></Protected>} />
      <Route path="/release" element={<Protected><PreDelivery /></Protected>} />
      <Route path="/forms" element={<Protected><FormsExport /></Protected>} />
      <Route path="/rolls" element={<Protected><StrandRolls /></Protected>} />
      <Route path="/tags" element={<Protected><CylinderTags /></Protected>} />
      <Route path="/measure" element={<Protected><ARMeasure /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
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
