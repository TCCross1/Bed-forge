export const PLANT_MANAGER_ROLES = ["admin", "executive"];

export function isPlantManager(role) {
  return PLANT_MANAGER_ROLES.includes(role);
}

export function isSupervisor(role) {
  return role === "qc_supervisor";
}

export function isQcTech(role) {
  return role === "qc_tech";
}

export function canSeeBlueprints(role) {
  return isPlantManager(role) || isSupervisor(role);
}

export function canSeeJobsCabinet(role) {
  return isPlantManager(role) || isSupervisor(role);
}

export function canSeeCommandTv(role) {
  return isPlantManager(role) || isSupervisor(role);
}

export function canSeePlanner(role) {
  return isPlantManager(role) || isSupervisor(role) || role === "production";
}

export function canSeePackages(role) {
  return isPlantManager(role) || isSupervisor(role);
}

export function canSeeBatch(role) {
  return isPlantManager(role) || role === "production";
}

export function canSeeFinance(role) {
  return isPlantManager(role);
}

export function jobListParams(openJob) {
  return openJob?.id ? { job_id: openJob.id } : {};
}
