import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import api, { API } from "../lib/api";

const DEFAULT = {
  company_name: "PRESTRESS SERVICES INDUSTRIES LLC",
  app_name: "BedForge QC",
  tag_header: "",
  has_logo: false,
  logo_url: "",
  updated_at: "",
};

const CompanyContext = createContext({
  ...DEFAULT,
  logoSrc: "",
  reload: () => {},
});

export function CompanyProvider({ children }) {
  const [company, setCompany] = useState(DEFAULT);

  const reload = useCallback(async () => {
    try {
      const { data } = await api.get("/company/public");
      setCompany({ ...DEFAULT, ...data });
    } catch (err) {
      console.error("[company] public load failed", err);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const logoSrc = company.has_logo
    ? `${API}/company/logo?v=${encodeURIComponent(company.updated_at || "1")}`
    : "";

  return (
    <CompanyContext.Provider value={{ ...company, logoSrc, reload }}>
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany() {
  return useContext(CompanyContext);
}
