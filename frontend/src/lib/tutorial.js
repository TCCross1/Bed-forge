/** In-app Master Tutorial — bundled, searchable, no network required. */

export const TUTORIAL_SECTION_IDS = [
  "what", "morning", "beds", "tension", "fresh", "batch", "qc", "ncr", "tags", "supervisors", "security", "problems",
];

export const TUTORIAL_SECTIONS = [
  {
    id: "what",
    title: "1. What BedForge is (and the problem it solves)",
    why: "Clipboards get wet, heat numbers get guessed, and nobody can prove what happened on a bed six months later. BedForge is the plant’s memory.",
    body: [
      "BedForge is the plant’s paperless quality-control and digital-twin system. Every beam, strand roll, tension reading, inspection, camber shot, finish check, and shipping sign-off lives in one record instead of wire-tied sheets and tribal knowledge.",
      "You still do the craft. The software remembers it — from the mill tag on the strand reel to the QR code tied on the finished girder.",
      "Think of one girder walking the plant. BedForge follows that same path: photograph the mill tag → put the beam on a bed → tension against a real twin of the shop drawing → inspect → camber and strength → finish → cylinder tags and beam QR → pre-delivery → owner/DOT package.",
      "The plant already survived a serious cyber intrusion that stopped production. BedForge is built so a stolen laptop or a guessed password cannot quietly rewrite heat numbers, unlock a bed, or erase an audit trail. If something changes, we can see who did it, when, and what it looked like before.",
    ],
  },
  {
    id: "morning",
    title: "2. Your first morning — log strand rolls by photo",
    why: "If you skip the heat number and a strand breaks, we cannot prove which heat was on the bed. That is an NCR, a forensic hole, and a DOT problem.",
    body: [
      "Start on Rolls (bottom nav on iPhone, sidebar on iPad/Mac). Tap Scan Tag. Photograph the mill tag on the coil — heat, reel, lot, ASTM, grade, diameter. Take a second shot of the MTC if it is on a separate sheet.",
      "BedForge reads the photo. Confirm the heat number with your own eyes. If a field is yellow, it is low-confidence — type the number off the tag. Do not invent a heat to get past the screen.",
      "Then assign that confirmed roll to the bed (and pour) you are about to stress. Until at least one confirmed roll is linked, tensioning is locked. That is the compliance gate, not a suggestion.",
      "No plant Wi-Fi? The photo queues on this phone and extracts when you are back. The yellow Offline banner at the top tells you queued vs syncing vs synced.",
      "Gloves and dark beds: turn the flashlight on. Hold the tag flat. If the camera fails, use Upload. Same confirm → assign flow.",
      "Demo walk: log a roll, confirm heat, assign to the tensioning bed, then go to Tension. If the gate still blocks you, the roll is not confirmed or not on that bed — fix the roll, do not guess.",
    ],
  },
  {
    id: "beds",
    title: "3. Putting beams on beds",
    why: "A beam with no bed is a rumor. Occupancy, marked end, and neighbors have to be true before anyone tensions or pours.",
    body: [
      "Open Planner. You will see the plant’s beds and the day’s assignments. Drag a planned beam onto a bed and day. The board will refuse a packing conflict (too long for the leftover bed, overlapping station).",
      "Set the marked end toward the header or the bulkhead — that is the origin every tape shot and every twin station is measured from. If Marked End is wrong, every layout number is wrong.",
      "The Live Board (home) shows all eight beds. Tap a bed to plan. Tap a beam mark to open its twin. Today’s plant path on the Board is the clean demo walk: rolls → planner → tension → inspect → camber → tags → release → DOT package.",
      "The dedicated demo girder is L25390-B1 — KYTC Type 2, Larue County shop drawing. That is the twin you should tension against in training.",
    ],
  },
  {
    id: "tension",
    title: "4. Tensioning the right way",
    why: "±5% elongation is how we prove the strand saw the force the drawing called for. A pretty average on a clipboard is not a record. Per-strand capture is.",
    body: [
      "Open Tension. Pick the beam (L25390-B1 on the demo plant). You will see the 3D tension twin — not a colored box. End view is the Marked End strand pattern from the shop drawing: 12 straight in the 18\" bottom flange at 2\" and 4\" soffit on a 2\" grid, plus 8 draped in the web at ±2\".",
      "Flip to the draped profile. Eight harped strands rise to 18 / 22 / 26 / 30 inches at the ends and depress through Dayton/Richmond H-56-S hold-downs at 29'-4\" and 44'-0\" from Marked End. The clamps sit at ±2\" off web centerline, matching those draped strands. Tap a strand to enter measured elongation. Tap a hold-down to set its status.",
      "If the yellow gate says the mill tag is missing: go back to Rolls. Do not type a fake heat. A plant manager can override with a written reason — that override is logged forever and is for broken tags and plant emergencies, not convenience.",
      "Jacking force and elongation are recorded against the mill-traceable roll. Within ±5% is pass. Outside is fail — stop and call a supervisor. Mark a strand N/A only if it is truly not in this pull.",
      "The twin is not a video game. If the twin and the sheet disagree, the sheet wins until a supervisor corrects and re-locks the BeamSpec.",
    ],
  },
  {
    id: "fresh",
    title: "5. Fresh concrete at delivery — spread, slump, and J-ring",
    why: "The truck is on the clock. If you do not record plastic concrete before it hits the bed, the mix that went around the strands is a rumor. Spread, slump, and J-ring are how we prove the load was placeable — not the cylinder crush you do later.",
    body: [
      "Open Fresh Test in one tap: gold Fresh on the iPhone tab bar, Fresh Test in the sidebar, first item in More, or the Truck’s here card on the Board. Job and pour are dropdowns. Last pour is remembered. L25390-B1 prefills on the demo plant.",
      "This plant pours SCC, so the default test is Spread (slump-flow, ASTM C1611) — two orthogonal diameters, live average. T50/T20 and visual stability (stable / minor halo / segregation) are optional. Spec min/max stay blank unless the mix ticket has a window.",
      "Slump (ASTM C143) is still there. Some states still call the cone. Do not default to it here; tap Slump if that ticket needs it.",
      "J-ring (ASTM C1621 / AASHTO T 345) is passing ability — will this mix get through strand and rebar without blocking. Record unconstrained spread (reused if you already typed it), two J-ring diameters, and the difference Δ. 0–1 in is PASS (no visible blocking), 1–2 in is BORDERLINE, over 2 in is BLOCKING. Default apparatus note is standard J-ring.",
      "Same ticket also takes mix/ticket number, concrete temperature, air if you take it, truck/load, time sampled (stamp now), Pass/Fail/Hold, and your name. Save and stay — the next truck on this pour is one more tap. Dead-zone beds still capture; the write queues offline.",
      "This is not cylinder tags and not a crush. Cylinders are hardened strength later. Fresh Test is plastic concrete at the chute, before the bed is poured. The mixer-side twin of this ticket is Batch Plant.",
    ],
  },
  {
    id: "batch",
    title: "6. Batch plant — the mixer record",
    why: "If we cannot say which mix, which weather, and which admixture dosages went into a girder, a failed cylinder or a low-air day becomes an NCR we cannot close.",
    body: [
      "Open Batch Plant from the desk sidebar or More on the phone. Production (mixer) drafts. Plant manager (admin/executive) confirms. After confirm the ticket is frozen — corrections are a new revision with a written reason. Nobody deletes yesterday.",
      "Capture outdoor conditions (phone location + weather). If weather is down, flag it estimated/manual and type the numbers. Never wait on the API while the mixer is charged.",
      "Link the Fresh Test for this load instead of retyping spread, air, and temperature. Link cylinders when the breaks come in — even after confirm, linking QC is allowed because strength arrives days later.",
      "The analyst looks at heat, dryness, air, w/cm, and history. It may say “bump AEA.” It cannot write dosages, confirm a batch, or override a gate.",
    ],
  },
  {
    id: "qc",
    title: "7. Inspection, camber, finish, and release",
    why: "These four sheets are how we prove the girder was built, stripped, measured, and allowed to leave. Skip one and the dossier has a hole.",
    body: [
      "Inspection (QIR): open Inspect. Pick the beam (dossier links pass ?beam= so you land on the right girder). Walk the sections — layout, reinforcement, hardware, concrete, strip, finish. Each section needs a PASS / FAIL / HOLD gate. Fail or hold updates the beam’s QC state. Work it on the iPhone; buttons are full-width.",
      "Digital tape (optional, same beam): open Digital Tape from More, the desk sidebar, or the Board tape card — not the gold Fresh Test tab. Browser tape is camera + gravity, not ARKit and not LiDAR. The iPhone plugin is ARKit (LiDAR only if the hardware has it). Calibrate this device against a known length; ±0.15% pass unlocks this phone for 24 hours with a per-device scale. Expired or failed cal blocks measuring (409). Plot origin at Marked End / header. Walk the beam and snap stations when the line is green. BedForge compares those shots to the locked twin. If it flags a rescan, walk back. Do not type a friendlier number.",
      "Camber / strength: after release strength. Three points — Marked End, midspan, Unmarked End — plus required vs release psi. On L25390 the drawing calls 4,500 psi release and 1.25\" design camber; those prefill when you open that beam. If release strength is short, you do not ship.",
      "Finish sheet: post-pour checklist. Strands cut/recessed/grouted, hardware, surface, lifting devices. Marked End ID is required — it should match the spec (L25390 / L25390-B1 / ME on the demo). Verify it on the beam, not from memory.",
      "Pre-delivery: last gate before the truck. Dimensional, camber, finish, hardware, marked-end, cracks documented. Truck number, destination, three sign-offs (QC, production, carrier). Incomplete checks will not release. Crush or predicted strength must meet required psi — an NCR does not bypass that gate.",
      "NCR: every fail, hold, twin pin, low break, or mix deviation becomes one closable record. File from the fail toast or /ncr. Any signed-in tech can create. Major/Critical need root cause, corrective action, and supervisor verification to close. Photos except documentation-only. Closed records are immutable until a supervisor reopens with a written reason.",
    ],
  },
  {
    id: "ncr",
    title: "7b. Non-conformance reports (NCR)",
    why: "A fail without a closable record is a rumor. Root cause is how we stop the next one — and how we answer a DOT years later.",
    body: [
      "Open NCR from the Board count (open list), Review & release in the sidebar, More on the phone, or the File NCR toast after a fail — fresh test, cylinder, QIR, tension, camber, finish, or a twin pin. Do not look for it on the gold Fresh Test field tab; that tab stays Fresh.",
      "Workflow: Open → Investigating → Corrective action → Verification → Closed. QC can file. Supervisors and plant managers close Major and Critical. You cannot close Major/Critical without a written root cause — the server returns 409 and the desk toasts it. Minor can close on a lighter path once photos are on file (except documentation-only).",
      "Photos attach the same way mill-tag photos do: encrypted in the plant vault, served by name, never logged as bytes. Filing the same fail twice returns the open NCR instead of a duplicate. Closed records are immutable until a supervisor reopens with a written reason. An NCR does not bypass tension or release gates. The analyst may show frequency — it never auto-closes and never changes the mix.",
    ],
  },
  {
    id: "tags",
    title: "8. Cylinder tags and beam QR codes",
    why: "Cylinders without a beam mark are orphan lab data. A girder without a QR is anonymous in the yard six months from now.",
    body: [
      "Cylinder Tags: morning setup — jobs, beam marks, break ages. Print at Actual Size / 100%. The company logo (uploaded once under branding) prints on every tag. Crush results later feed the camber / strength story and the release forecast on the Board.",
      "Beam QR: every beam gets a permanent token when it is created. QR Labels prints laminate tags — logo, job, mark, QR. Reprint one beam any time from the twin or dossier.",
      "Scan QR in-app (or the phone camera) opens /b/{token}. In the field, unsigned, you get specs, status, drawings, view-only twin. Signed-in QC gets the full history. The token is not a plant password — it only unlocks that one beam.",
      "If a laminate prints inverted or dark, the in-app scanner tries both inversions. Hold steady, use the flashlight, or upload a photo of the tag.",
    ],
  },
  {
    id: "supervisors",
    title: "9. What supervisors and managers can do",
    why: "Least privilege is the rule. Extra keys exist for the people who already sign the plant’s name on DOT paper — and every extra key is audited.",
    body: [
      "QC Tech: log rolls, inspect, digital tape, fill sheets, scan QR. Cannot change accounts, unlock a locked spec, or turn off security.",
      "Production: plan beds, run tension, print tags. Cannot approve QC locks or manage users.",
      "QC Supervisor: lock BeamSpecs, brand cylinder/QR labels, review holds. Cannot disable plant-manager accounts or change the office IP allow-list.",
      "Plant Manager / Executive: see every bed, override a gate with a written reason (bed number is enough — type 3, not a UUID), manage users and devices, search history, export packages, take backups. Command → Overrides. Revoke a lost phone under Devices. Every one of those actions is written to an append-only audit log.",
      "Owner packages: Packages → pick the pour → generate. One branded PDF (and Excel) with QIR, tension, camber, finish, pre-delivery, strand heats, drawings, photos. Stored against the pour. Print any package from that desk.",
      "Financial signals (managers only): open NCRs / rework estimate, bed-days at risk, scrap tally. It is a signal, not a job-cost system.",
      "Forge Coach cannot issue overrides, unlock beds, or pass QC for you. It will tell you who can, and that a written reason hits the audit log.",
    ],
  },
  {
    id: "security",
    title: "10. Why the system is locked down (plain language)",
    why: "After the intrusion we assume laptops get stolen and passwords get phished. Locks are how the plant keeps producing instead of explaining a forged heat number to a DOT.",
    body: [
      "Sign-in creates a session we can kill. Idle timeout. Optional device binding. Optional office/VPN IP allow-list for plant-manager tools so a stolen admin session on a coffee-shop network cannot change users.",
      "There is no standing shared admin password on a shop PC. Demo logins exist only on development plants. Open self-registration is off. Failed sign-ins lock the account after repeated tries.",
      "In transit: HTTPS. At rest: drawings, mill photos, and logos are encrypted on disk. Passwords are hashed (never stored as text). Secrets live in environment variables, not in git.",
      "Shop drawings require a login (or a beam QR token scoped to that one beam). Exports and backups are logged: who, what, when. The audit log is append-only. Nobody gets an API to quietly edit yesterday.",
      "The strand-roll gate, locked BeamSpecs, and pre-delivery checks are the same idea as a lock on the mill-cert file cabinet — except they cannot be shoulder-surfed and they keep a who/when.",
    ],
  },
  {
    id: "problems",
    title: "11. What to do when something goes wrong",
    why: "The wrong fix (fake heat, force-pass, delete the log) is worse than the original miss. Stop, say it, log it.",
    body: [
      "Forgot password or locked out: a plant manager resets or re-enables you. They cannot see your old password.",
      "Lost phone / stolen iPad: plant manager → Command → People or Devices → Revoke. Sessions for that person or device die immediately.",
      "Tension gate blocked: log the strand roll. Do not type a fake heat. Override is a last resort with a written reason.",
      "Twin looks wrong: compare to the shop drawing. Ask a supervisor to correct and lock the spec.",
      "Digital tape flagged a rescan: walk back, wait for the green laser line, snap again. A forced shot stays marked. If the tape is locked, this phone’s daily calibration expired or failed ±0.15% — recalibrate this device, not someone else’s.",
      "Offline banner stuck on queued: get on plant Wi-Fi and tap Retry. Photos and sheets are on this device until they sync. Do not delete the app.",
      "QR will not scan: flashlight, hold still, or upload a photo. In-app scan tries inverted codes used on dark laminates.",
      "Suspect an attack: disconnect the affected PC, revoke users from a known-good manager device, take a backup, restore onto clean hardware — never onto the attacked host. Call plant management. The audit log is evidence; do not delete it.",
    ],
  },
];

export function tutorialSectionById(id) {
  return TUTORIAL_SECTIONS.find((s) => s.id === id) || null;
}

export function searchTutorial(q) {
  const needle = String(q || "").trim().toLowerCase();
  if (!needle) return TUTORIAL_SECTIONS;
  return TUTORIAL_SECTIONS.filter((section) => {
    const blob = [section.id, section.title, section.why, ...(section.body || [])].join(" ").toLowerCase();
    return blob.includes(needle);
  });
}
