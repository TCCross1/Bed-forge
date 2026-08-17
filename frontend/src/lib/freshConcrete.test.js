import {
  applyComputedFields,
  blockingAssessment,
  blockingDelta,
  diameterAverage,
  pickIdentity,
} from "./freshConcrete";

test("spread average uses both orthogonal diameters", () => {
  expect(diameterAverage(26, 28)).toBe(27);
  expect(diameterAverage("24.5", "25.5")).toBe(25);
  expect(diameterAverage(27, "")).toBe(27);
  expect(diameterAverage("", "")).toBeNull();
});

test("J-ring blocking bands match ASTM C1621", () => {
  expect(blockingAssessment(0).code).toBe("pass");
  expect(blockingAssessment(1).label).toBe("PASS");
  expect(blockingAssessment(1.01).code).toBe("borderline");
  expect(blockingAssessment(2).label).toBe("BORDERLINE");
  expect(blockingAssessment(2.01).code).toBe("blocking");
  expect(blockingAssessment(3.5).label).toBe("BLOCKING");
  expect(blockingAssessment(-0.25).code).toBe("pass");
  expect(blockingAssessment(null)).toBeNull();
});

test("blocking delta is unconstrained minus J-ring", () => {
  expect(blockingDelta(28, 26.5)).toBe(1.5);
  expect(blockingDelta(27, 27)).toBe(0);
  expect(blockingDelta(null, 26)).toBeNull();
});

test("J-ring reuses spread average as unconstrained flow", () => {
  const out = applyComputedFields({
    spread_d1_in: 27,
    spread_d2_in: 29,
    jring_d1_in: 25,
    jring_d2_in: 25,
  });
  expect(out.spread_avg_in).toBe(28);
  expect(out.unconstrained_avg_in).toBe(28);
  expect(out.jring_avg_in).toBe(25);
  expect(out.blocking_delta_in).toBe(3);
  expect(out.blocking_assessment).toBe("blocking");
  expect(out.blocking_label).toBe("BLOCKING");
});

test("single beam on the pour is preselected", () => {
  const picked = pickIdentity({
    jobs: [{ id: "j1", job_number: "L25390" }],
    pours: [{ id: "p1", job_id: "j1", pour_number: "P-1" }],
    beams: [{ id: "b1", mark: "L25390-B1", job_id: "j1", pour_id: "p1", bed_id: "bed1" }],
    beds: [{ id: "bed1", status: "casting" }],
    query: { job: "L25390", pour: "P-1" },
    last: {},
  });
  expect(picked.jobId).toBe("j1");
  expect(picked.pourId).toBe("p1");
  expect(picked.beamIds).toEqual(["b1"]);
  expect(picked.bedId).toBe("bed1");
});
