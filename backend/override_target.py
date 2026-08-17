"""Resolve plant-manager override targets from bed numbers, marks, or UUIDs."""


class OverrideTargetError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def classify_override_target(kind: str, raw: str) -> dict:
    """Map an override kind + typed target to a Mongo lookup.

    Strand-tension overrides are issued against a bed. Plant managers type the
    bed number (1–8) on the floor; UUIDs still work. QC force accepts a beam
    mark. Spec unlock accepts a BeamSpec id.
    """
    value = (raw or "").strip()
    if not value:
        raise OverrideTargetError("Target is required")
    if kind == "strand_tension":
        if value.isdigit():
            return {"collection": "beds", "query": {"bed_number": int(value)}, "label": f"bed {value}"}
        return {"collection": "beds", "query": {"id": value}, "label": "bed"}
    if kind == "spec_unlock":
        return {
            "collection": "beam_specs",
            "query": {"id": value},
            "alt_query": {"beam_mark": value},
            "label": "BeamSpec",
        }
    if kind == "qc_force":
        return {
            "collection": "beams",
            "query": {"id": value},
            "alt_query": {"mark": value},
            "label": "beam",
        }
    raise OverrideTargetError("Unknown override kind")
