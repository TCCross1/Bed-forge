import { useSearchParams } from "react-router-dom";

/** Beam UUID from `?beam=` so QIR / camber / finish / release honor dossier links. */
export function useBeamQuery() {
  const [params] = useSearchParams();
  return params.get("beam") || "";
}

export function pickBeamId(current, queryBeam, beams) {
  if (current && (beams || []).some((b) => b.id === current)) return current;
  if (queryBeam && (beams || []).some((b) => b.id === queryBeam)) return queryBeam;
  return current || queryBeam || (beams && beams[0] && beams[0].id) || "";
}
