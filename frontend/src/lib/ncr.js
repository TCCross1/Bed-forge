/** NCR helpers — draft URLs and fail-prompt toasts. Never bypasses tension/release gates. */
import { toast } from "sonner";

export const NCR_CATEGORIES = [
  { id: "visual", label: "Visual" },
  { id: "dimensional", label: "Dimensional" },
  { id: "material", label: "Material" },
  { id: "process", label: "Process" },
  { id: "documentation", label: "Documentation" },
  { id: "strand", label: "Strand" },
  { id: "hardware", label: "Hardware / insert" },
  { id: "batch", label: "Batch / mix" },
];

export const NCR_SEVERITIES = [
  { id: "minor", label: "Minor", color: "#FFD600" },
  { id: "major", label: "Major", color: "#FF9100" },
  { id: "critical", label: "Critical", color: "#FF3366" },
];

export const NCR_STATUSES = [
  { id: "open", label: "Open", next: "investigating" },
  { id: "investigating", label: "Under investigation", next: "corrective_action" },
  { id: "corrective_action", label: "Corrective action", next: "verification" },
  { id: "verification", label: "Verification", next: "closed" },
  { id: "closed", label: "Closed", next: null },
  { id: "rejected", label: "Rejected", next: null },
];

export function canManageNcr(role) {
  return ["qc_supervisor", "admin", "executive"].includes(role);
}

export function ncrDraftUrl(prompt = {}) {
  const q = new URLSearchParams();
  if (prompt.ncr_id) q.set("id", prompt.ncr_id);
  if (prompt.beam_id) q.set("beam", prompt.beam_id);
  if (prompt.bed_id) q.set("bed", prompt.bed_id);
  if (prompt.pour_id) q.set("pour", prompt.pour_id);
  if (prompt.job_id) q.set("job", prompt.job_id);
  if (prompt.batch_id) q.set("batch", prompt.batch_id);
  if (prompt.source_type) q.set("source", prompt.source_type);
  if (prompt.source_id) q.set("source_id", prompt.source_id);
  if (prompt.category) q.set("category", prompt.category);
  if (prompt.severity) q.set("severity", prompt.severity);
  if (prompt.description) q.set("desc", prompt.description);
  return `/ncr?${q.toString()}`;
}

export function toastNcrPrompt(prompt) {
  if (!prompt) return;
  toast.warning(prompt.title || "File an NCR for this fail", {
    duration: 14000,
    action: {
      label: prompt.ncr_id ? "Open NCR" : "File NCR",
      onClick: () => {
        window.location.href = ncrDraftUrl(prompt);
      },
    },
  });
}

export function toastNcrFromResponse(data) {
  if (data?.ncr_prompt) toastNcrPrompt(data.ncr_prompt);
}

export function toastNcrFromError(err) {
  const detail = err?.response?.data?.detail;
  if (detail && typeof detail === "object" && detail.ncr_prompt) {
    toastNcrPrompt(detail.ncr_prompt);
  }
}
