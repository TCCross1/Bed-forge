import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import { useAuth } from "./AuthContext";

const OpenJobContext = createContext({
  jobs: [],
  openJob: null,
  pours: [],
  pourDate: "",
  marks: [],
  privileges: {},
  activeMark: "",
  ready: false,
  refresh: async () => {},
  openJobById: async () => {},
  setActiveMark: () => {},
  setPourDate: () => {},
});

export function OpenJobProvider({ children }) {
  const { user, ready: authReady } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [openJob, setOpenJob] = useState(null);
  const [pours, setPours] = useState([]);
  const [marks, setMarks] = useState([]);
  const [privileges, setPrivileges] = useState({});
  const [activeMark, setActiveMark] = useState("");
  const [pourDate, setPourDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) {
      setJobs([]);
      setOpenJob(null);
      setPours([]);
      setMarks([]);
      setPrivileges({});
      setReady(true);
      return;
    }
    try {
      const [jobsRes, openRes] = await Promise.all([
        api.get("/jobs"),
        api.get("/jobs/open"),
      ]);
      setJobs(Array.isArray(jobsRes.data) ? jobsRes.data : []);
      const payload = openRes.data || {};
      setOpenJob(payload.job || null);
      const nextPours = Array.isArray(payload.pours) ? payload.pours : [];
      setPours(nextPours);
      setMarks(Array.isArray(payload.marks) ? payload.marks : []);
      setPrivileges(payload.privileges || {});
      const activePour = nextPours.find((item) => item.status === "active") || nextPours[0];
      if (activePour?.pour_date) setPourDate(activePour.pour_date);
    } catch (err) {
      console.error("[open-job] refresh failed", err);
    } finally {
      setReady(true);
    }
  }, [user]);

  useEffect(() => {
    if (!authReady) return undefined;
    refresh();
    return undefined;
  }, [authReady, refresh]);

  const openJobById = useCallback(async (jobId) => {
    if (!jobId) return;
    const { data } = await api.put("/jobs/open", { job_id: jobId });
    setOpenJob(data.job || null);
    setPours(Array.isArray(data.pours) ? data.pours : []);
    setMarks(Array.isArray(data.marks) ? data.marks : []);
    setPrivileges(data.privileges || {});
    setActiveMark("");
    const activePour = (Array.isArray(data.pours) ? data.pours : []).find((item) => item.status === "active") || (data.pours || [])[0];
    if (activePour?.pour_date) setPourDate(activePour.pour_date);
    await refresh();
  }, [refresh]);

  const value = useMemo(() => ({
    jobs,
    openJob,
    pours,
    pourDate,
    marks,
    privileges,
    activeMark,
    ready,
    refresh,
    openJobById,
    setActiveMark,
    setPourDate,
  }), [jobs, openJob, pours, pourDate, marks, privileges, activeMark, ready, refresh, openJobById]);

  return <OpenJobContext.Provider value={value}>{children}</OpenJobContext.Provider>;
}

export function useOpenJob() {
  return useContext(OpenJobContext);
}
