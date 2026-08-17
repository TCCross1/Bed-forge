import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import DigitalTwin from "./pages/DigitalTwin";
import NewInspection from "./pages/NewInspection";
import TensionCalculator from "./pages/TensionCalculator";
import FormsExport from "./pages/FormsExport";
import NCRBoard from "./pages/NCRBoard";
import BatchPlant from "./pages/BatchPlant";
import Licensing from "./pages/Licensing";

function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready || user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/twin" element={<Protected><DigitalTwin /></Protected>} />
      <Route path="/inspection" element={<Protected><NewInspection /></Protected>} />
      <Route path="/tension" element={<Protected><TensionCalculator /></Protected>} />
      <Route path="/forms" element={<Protected><FormsExport /></Protected>} />
      <Route path="/ncr" element={<Protected><NCRBoard /></Protected>} />
      <Route path="/batch" element={<Protected><BatchPlant /></Protected>} />
      <Route path="/licensing" element={<Protected><Licensing /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
        <Toaster theme="dark" position="top-right" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
