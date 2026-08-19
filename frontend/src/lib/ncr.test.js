import {
  canCloseNcr,
  canCreateNcr,
  canManageNcr,
  ncrDraftUrl,
  ncrPhotoPath,
} from "./ncr";

test("draft URL prefills source so a fail toast is one tap", () => {
  const url = ncrDraftUrl({
    source_type: "fresh",
    source_id: "ft-1",
    category: "material",
    severity: "major",
    description: "gate=fail",
    beam_id: "b1",
    job_id: "j1",
    pour_id: "p1",
  });
  expect(url.startsWith("/ncr?")).toBe(true);
  expect(url).toContain("source=fresh");
  expect(url).toContain("source_id=ft-1");
  expect(url).toContain("severity=major");
  expect(url).toContain("beam=b1");
});

test("existing NCR id opens the record instead of a second draft", () => {
  const url = ncrDraftUrl({ ncr_id: "ncr-open", source_type: "anomaly" });
  expect(url).toContain("id=ncr-open");
});

test("roles match plant: QC files, supervisors close Major", () => {
  expect(canCreateNcr("qc_tech")).toBe(true);
  expect(canManageNcr("qc_tech")).toBe(false);
  expect(canCloseNcr("qc_tech", "minor")).toBe(true);
  expect(canCloseNcr("qc_tech", "major")).toBe(false);
  expect(canCloseNcr("qc_supervisor", "major")).toBe(true);
  expect(canCloseNcr("admin", "critical")).toBe(true);
});

test("photo path is a named file, not embedded bytes", () => {
  expect(ncrPhotoPath("abc", "ncr-abc-1.jpg")).toBe("/ncrs/abc/photos/ncr-abc-1.jpg");
  expect(ncrPhotoPath("", "x.jpg")).toBe("");
});
