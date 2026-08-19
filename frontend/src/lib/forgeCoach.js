/** Forge Coach — grounded prestress QC knowledge, route scripts, local answers. Offline-first. */

import { TUTORIAL_SECTIONS } from "./tutorial";

export const COACH_NAME = "Forge Coach";

export const ARTICLES = [
  {
    id: "heat",
    tags: ["roll", "heat", "mill", "tag", "strand", "gate", "ocr", "photo", "reel", "morning"],
    title: "Strand heat logs",
    tutorial: "morning",
    route: "/rolls",
    body: "Photograph the mill tag on Rolls → confirm heat/reel/grade with your eyes → assign to the bed. If you skip the heat number and a strand breaks, we cannot prove which heat was on the bed. Tensioning stays locked until at least one confirmed roll is linked. Do not invent a heat.",
  },
  {
    id: "elongation",
    tags: ["tension", "elongation", "5%", "jacking", "strand", "twin", "l25390"],
    title: "±5% elongation",
    tutorial: "tension",
    route: "/tension",
    body: "Each strand is tappable on the tension twin. Enter measured elongation against theoretical. Within ±5% is pass. Outside is fail — stop and get a supervisor. A clipboard average is not a record. Per-strand capture is how we prove the drawing’s jacking force actually hit the steel.",
  },
  {
    id: "marked-end",
    tags: ["marked", "end", "me", "header", "origin", "finish"],
    title: "Marked End",
    tutorial: "beds",
    route: "/planner",
    body: "Marked End is the origin. Every twin station, tape shot, and finish ID is measured from it. Set it on the planner (toward header or bulkhead). Verify the stamped ID on the finish sheet. If ME is backwards, every number on the girder is backwards.",
  },
  {
    id: "camber",
    tags: ["camber", "strength", "release", "psi", "midspan"],
    title: "Camber points",
    tutorial: "qc",
    route: "/camber",
    body: "Three points after release strength: Marked End, midspan, Unmarked End, plus required vs measured psi. L25390 calls 4,500 psi release and 1.25\" design camber. If release strength is short, the beam does not ship.",
  },
  {
    id: "finish",
    tags: ["finish", "grout", "strand pocket", "surface", "hardware"],
    title: "Finish sheet",
    tutorial: "qc",
    route: "/finish",
    body: "Post-pour checklist: strands cut/recessed/grouted, hardware complete, surface accepted, lifting devices, Marked End ID required. Land from the dossier with ?beam= so you are on the right girder.",
  },
  {
    id: "release",
    tags: ["pre-delivery", "release", "truck", "signoff", "ship"],
    title: "Pre-delivery gate",
    tutorial: "qc",
    route: "/release",
    body: "Last gate before the truck. Checks plus truck, destination, and three sign-offs (QC, production, carrier). Incomplete will not release. That protects the plant when a girder shows up at the site missing hardware.",
  },
  {
    id: "twin",
    tags: ["twin", "hold-down", "h-56", "drape", "l25390", "kytc", "type 2"],
    title: "Tension twin (L25390 Type 2)",
    tutorial: "tension",
    route: "/tension",
    body: "KYTC Type 2 / L25390: 20 strands — 12 straight in the 18\" flange at 2\"/4\" soffit on a 2\" grid (±1,3,5\"), 8 draped in the web at ±2\" peaking 18/22/26/30\" at the ends, depressed through H-56-S hold-downs at 29'-4\" and 44'-0\" ME. Clamps are a pair at ±2\" off centerline. Tap every strand and every hold-down. Sheet wins if twin and drawing disagree.",
  },
  {
    id: "qr",
    tags: ["qr", "scan", "laminate", "dossier", "token"],
    title: "Beam QR",
    tutorial: "tags",
    route: "/qr",
    body: "Permanent identity on the girder. Print laminate tags (logo + job + mark + QR). Scan in-app or with the phone camera. Field scan without login shows specs; signed-in QC sees history. Token is not a plant password.",
  },
  {
    id: "cylinders",
    tags: ["cylinder", "tag", "crush", "break", "lab"],
    title: "Cylinder tags",
    tutorial: "tags",
    route: "/tags",
    body: "Morning: jobs, beam marks, break ages, print Actual Size 100%. Logo prints when uploaded. Crush later feeds camber/strength and the Board’s release forecast. A cylinder with no beam mark is orphan lab data.",
  },
  {
    id: "spread",
    tags: ["spread", "slump", "j-ring", "jring", "truck", "fresh", "scc", "flow", "t50", "air", "blocking"],
    title: "Fresh test at the truck",
    tutorial: "fresh",
    route: "/fresh",
    body: "Truck’s here: tap gold Fresh on the field bar (or Fresh Test in More / sidebar). Job and pour are dropdowns — last pour is remembered. Default is Spread (SCC slump-flow). Tap Slump if the state still wants the cone. Tap J-Ring for passing ability; unconstrained spread is reused. Stamp time, save, stay for the next load.",
  },
  {
    id: "batch",
    tags: ["batch", "plant", "mixer", "mix", "aea", "w/cm", "weather", "air", "admixture", "confirm"],
    title: "Batch plant tickets",
    tutorial: "batch",
    route: "/batch",
    body: "Mixer office: Batch Plant. Draft the load — ingredients, w/cm, outdoor conditions (capture + override). Link the Fresh Test instead of retyping. Plant manager confirms; then it is permanent. Analyst may suggest AEA on a hot dry day. It never changes the mix. QC and production are read-only on confirmed tickets.",
  },
  {
    id: "ncr",
    tags: ["ncr", "nonconformance", "non-conformance", "defect", "anomaly", "hold", "fail", "root cause", "corrective"],
    title: "Non-conformance (NCR)",
    tutorial: "ncr",
    route: "/ncr",
    body: "Every fail becomes one record: twin pin, out-of-tolerance shot, fresh-test fail, low cylinder, or a tech filing by hand. Open NCR from the sidebar, Board open-count, More, or the File NCR toast after a fail. Workflow is open → investigating → corrective action → verification → closed. Photos for most categories. Major/Critical need root cause, CA, and supervisor verification — the server 409s a silent close. The analyst may show frequency — it never auto-closes and never changes the mix. An NCR does not bypass tension or release gates.",
  },
  {
    id: "tape",
    tags: ["tape", "digital", "calibrat", "arkit", "lidar", "scale", "camera", "measure", "0.15", "lock", "gravity"],
    title: "Digital tape and daily calibration",
    tutorial: "qc",
    route: "/measure",
    body: "Open Digital Tape from More on the phone, Tape Review in the desk sidebar, Board tape card, or a Tape button on twin/inspect — not the gold Fresh Test tab. Browser tape is camera + gravity, not ARKit and not LiDAR. The native iPhone plugin is the ARKit path (LiDAR only on supported hardware). Calibrate this device against a known length. It must land within ±0.15% or the tape stays locked. A pass unlocks this phone for 24 hours and stores a scale factor only for this device — never plant-wide. Expired cal 409s until you recalibrate. Who, when, device, known/measured, scale, and pass/fail are audited. Photos and GPS are not logged.",
  },
  {
    id: "override",
    tags: ["override", "unlock", "bypass", "gate", "command", "manager"],
    title: "Overrides",
    tutorial: "supervisors",
    route: "/command",
    body: "Forge Coach cannot issue overrides. A plant manager (Command → Overrides) types a bed number, a written reason, and that hits the append-only audit log. Use it for a destroyed mill tag or a plant emergency — not to skip logging the heat.",
  },
  {
    id: "offline",
    tags: ["offline", "sync", "wifi", "queue", "banner"],
    title: "Offline queue",
    tutorial: "problems",
    route: "/",
    body: "Field writes (inspection, tension captures, camber, finish, release, mill-tag confirm/assign) queue on this device when the network dies. The banner shows OFFLINE / SYNCING / queued / SYNCED. Photos are stored as files on the phone, not dropped. 409 tension-gate conflicts stay queued until a roll is on the bed.",
  },
  {
    id: "liability",
    tags: ["ncr", "dot", "forensic", "liability", "why", "trace"],
    title: "Why the paperwork exists",
    tutorial: "security",
    route: "/guide",
    body: "Heats, ±5%, marked end, camber, finish, and pre-delivery are how we answer a broken strand, a failed cylinder, or a site complaint years later. Without them you get an NCR you cannot close and a forensic hole. The locks are liability control, not software being difficult.",
  },
  {
    id: "floor",
    tags: ["gloves", "dark", "flashlight", "iphone", "ipad", "tip"],
    title: "Floor tips",
    tutorial: "problems",
    route: "/rolls",
    body: "Gloves on: use the big buttons (48px). Dark bed: flashlight on Scan Tag and QR. iPhone is the field set (bottom nav). iPad/Mac is command (sidebar). If something looks wrong on the twin, stop and compare to the sheet — do not keep capturing.",
  },
  {
    id: "day",
    tags: ["first", "day", "walkthrough", "demo", "path", "morning"],
    title: "First full day",
    tutorial: "what",
    route: "/",
    body: "Morning: Rolls — photo mill tags, confirm, assign. Planner — put beams on beds, set Marked End. Tension — twin, per-strand elongation, hold-down status (gate needs a roll). Inspect QIR. Camber + strength. Finish sheet. Cylinder tags + beam QR. Pre-delivery. Packages for the pour. That is the Board’s “today’s plant path.”",
  },
];

export const ROUTE_WALKS = {
  "/": [
    { testid: "plant-demo-path", label: "Today’s plant path — eight steps from mill tag to DOT package" },
    { testid: "board-scan-qr", label: "Scan a beam QR" },
    { testid: "nav-rolls", label: "Rolls — start the morning here" },
  ],
  "/rolls": [
    { testid: "scan-tag", label: "Scan Tag — photograph the mill tag" },
    { testid: "nav-tension", label: "After confirm + assign, go to Tension" },
  ],
  "/tension": [
    { testid: "tension-twin-canvas", label: "Twin — tap a strand or hold-down" },
    { testid: "tension-capture-panel", label: "Capture panel — elongation or hold-down status" },
    { testid: "strand-save", label: "Save strand (blocked until a roll is on the bed)" },
  ],
  "/inspection": [
    { testid: "inspection-beam-select", label: "Pick the beam under inspection" },
    { testid: "inspection-stepper", label: "Walk QIR sections in order" },
  ],
  "/camber": [
    { testid: "camber-beam", label: "Select the beam" },
    { testid: "camber-strength-gate", label: "Release strength vs required" },
  ],
  "/finish": [
    { testid: "finish-beam", label: "Select the beam" },
    { testid: "finish-marked-end", label: "Marked End ID — required" },
  ],
  "/release": [
    { testid: "pd-beam", label: "Select the beam leaving the plant" },
    { testid: "pd-release", label: "Release — only after checks, truck, and three sign-offs" },
  ],
  "/tags": [
    { testid: "nav-tags", label: "Cylinder tag generator" },
  ],
  "/qr": [
    { testid: "nav-qr", label: "Print laminate beam QR labels" },
  ],
  "/scan": [
    { testid: "nav-scan", label: "Scan a laminate — inverted codes are tried" },
  ],
  "/planner": [
    { testid: "nav-planner", label: "Drag beams onto beds and days" },
  ],
  "/command": [
    { testid: "forge-coach-open", label: "Coach cannot override — a plant manager uses Command → Overrides with a written reason" },
  ],
  "/guide": [
    { testid: "master-tutorial", label: "Search or open a section — this manual works offline" },
    { testid: "tutorial-search", label: "Search the manual" },
  ],
  "/packages": [
    { testid: "nav-packages", label: "Generate the branded DOT / owner package for a pour" },
  ],
  "/fresh": [
    { testid: "fresh-identity", label: "Job and pour dropdowns — last pour is remembered" },
    { testid: "fresh-type-spread", label: "Spread is the default for this SCC plant" },
    { testid: "fresh-save", label: "Save — stay for the next truck" },
  ],
  "/batch": [
    { testid: "batch-identity", label: "Job, pour, beams" },
    { testid: "batch-ingredients", label: "Weights and admixture dosages" },
    { testid: "batch-confirm", label: "Plant manager confirms — then it is permanent" },
  ],
  "/ncr": [
    { testid: "ncr-new", label: "File NCR — glove-size target" },
    { testid: "ncr-description", label: "Describe what you found" },
    { testid: "ncr-save", label: "File — then add photos and containment" },
    { testid: "ncr-root-cause", label: "Root cause — required to close Major" },
  ],
  "/measure": [
    { testid: "ar-honesty", label: "Honesty line — camera/gravity on web, ARKit only on the iPhone plugin" },
    { testid: "ar-cal-panel", label: "Daily calibration — known length vs this phone, ±0.15%" },
    { testid: "ar-cal-submit", label: "Calibrate this device — 24h lock, per-phone scale" },
    { testid: "ar-start", label: "Start digital tape — blocked until this device is in cal" },
  ],
};

const STOP = new Set(["the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it", "how", "what", "why", "do", "i", "we", "my", "this", "that"]);

export function tokenize(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9%+./'-]+/g, " ")
    .split(/\s+/)
    .filter((w) => w && !STOP.has(w) && w.length > 1);
}

export function retrieveArticles(question, limit = 4) {
  const tokens = tokenize(question);
  const scored = ARTICLES.map((article) => {
    const hay = tokenize([article.title, article.body, ...(article.tags || [])].join(" "));
    let score = 0;
    tokens.forEach((tok) => {
      if (hay.includes(tok)) score += 2;
      if ((article.tags || []).some((t) => t.includes(tok) || tok.includes(t))) score += 2;
      if ((article.title || "").toLowerCase().includes(tok)) score += 3;
    });
    return { article, score };
  }).filter((row) => row.score > 0);
  scored.sort((a, b) => b.score - a.score);
  if (!scored.length) return ARTICLES.filter((a) => a.id === "day").slice(0, limit);
  return scored.slice(0, limit).map((row) => row.article);
}

export function suggestedPrompts(route = "/", role = "qc_tech") {
  const path = String(route || "/").split("?")[0];
  const byRoute = {
    "/": ["Walk me through my first day", "Truck’s here — how do I log spread?", "Why do we log strand heats?"],
    "/fresh": ["Truck’s here — how do I log spread?", "What is J-ring?", "Walk me through this screen"],
    "/batch": ["How do I log a batch?", "Can the analyst change the mix?", "Who confirms a batch?"],
    "/rolls": ["How do I log a mill tag?", "What if the camera cannot read the heat?", "Why is tension locked?"],
    "/tension": ["Explain the L25390 strand pattern", "What is ±5%?", "Walk me through this screen"],
    "/inspection": ["How do I run a QIR?", "What does HOLD mean?"],
    "/camber": ["Which camber points do I take?", "What if release strength is short?"],
    "/finish": ["What is Marked End ID?", "Walk me through this screen"],
    "/ncr": ["How do I file an NCR?", "Who can close a Major?", "Walk me through this screen"],
    "/measure": ["How do I calibrate the tape?", "Is the browser tape ARKit?", "Walk me through this screen"],
    "/release": ["What is required before the truck leaves?"],
    "/tags": ["How do I print cylinder tags?"],
    "/qr": ["How do beam QR codes work?"],
    "/planner": ["How do I put a beam on a bed?"],
    "/command": ["Can you unlock the tension gate?", "How do overrides work?"],
    "/guide": ["Show me the security chapter", "What do I do when something goes wrong?"],
    "/packages": ["What is in the DOT package?"],
  };
  const base = byRoute[path] || ["Walk me through this screen", "Why does this step exist?", "Show me the tutorial"];
  if (role === "production") return ["How do I tension the right way?", "How do I assign a beam to a bed?", ...base].slice(0, 4);
  if (role === "qc_supervisor") return ["How do I lock a BeamSpec?", "What do I do on a HOLD?", ...base].slice(0, 4);
  if (role === "admin" || role === "executive") return ["How do I override with an audit trail?", "How do I revoke a lost phone?", ...base].slice(0, 4);
  return base.slice(0, 4);
}

export function walkForRoute(route = "/") {
  const path = String(route || "/").split("?")[0];
  return ROUTE_WALKS[path] || ROUTE_WALKS["/"] || [];
}

function isOverrideAsk(question) {
  const q = String(question || "").toLowerCase();
  return /override|unlock (the )?(bed|gate|spec)|bypass|force pass|turn off the gate/.test(q);
}

export function localAnswer(question, route = "/", role = "qc_tech") {
  const q = String(question || "").trim();
  if (isOverrideAsk(q)) {
    return {
      source: "local",
      text: "I cannot issue an override, unlock a bed, or force QC. A plant manager does that in Command → Overrides: bed number (or beam mark), a written reason, and it is written to the audit log. If the mill tag is readable, log the roll instead — that is the real fix.",
      tutorial: "supervisors",
      highlights: walkForRoute("/command").slice(0, 1),
      articles: retrieveArticles(q),
    };
  }
  const walkAsk = /walk me|this screen|where do i tap|show me (this|the screen)|point to/.test(q.toLowerCase());
  if (walkAsk) {
    const steps = walkForRoute(route);
    const lines = steps.map((s, i) => `${i + 1}. ${s.label}.`);
    return {
      source: "local",
      text: lines.length
        ? `On this screen, in order:\n${lines.join("\n")}\nTap Next highlight and I will ring the control. Gloves on — they are full-size targets.`
        : "Open the matching tutorial section and I will walk the buttons on that page.",
      tutorial: null,
      highlights: steps,
      articles: retrieveArticles(q),
    };
  }
  if (/truck'?s here|log spread|slump flow|j-?ring|fresh test/.test(q.toLowerCase())) {
    return {
      source: "local",
      text: retrieveArticles("fresh spread truck")[0]?.body
        + " Open Fresh. Measure two diameters. Save. J-ring is the difference between unconstrained spread and the ring flow.",
      tutorial: "fresh",
      navigateTo: "/fresh",
      highlights: walkForRoute("/fresh"),
      articles: retrieveArticles("spread j-ring"),
    };
  }
  if (/log a batch|batch plant|can the analyst change|who confirms a batch/.test(q.toLowerCase())) {
    return {
      source: "local",
      text: retrieveArticles("batch plant mixer")[0]?.body
        + " The analyst cannot confirm a batch or change dosages. Production drafts. Admin/executive confirms.",
      tutorial: "batch",
      navigateTo: "/batch",
      highlights: walkForRoute("/batch"),
      articles: retrieveArticles("batch mix"),
    };
  }
  if (/file an ncr|non-?conformance|who can close a major|ncr desk/.test(q.toLowerCase())) {
    return {
      source: "local",
      text: retrieveArticles("ncr nonconformance")[0]?.body
        + " Open NCR. Any tech can file. Major and Critical stay open until a supervisor verifies root cause. The toast after a fail is the fastest path.",
      tutorial: "ncr",
      navigateTo: "/ncr",
      highlights: walkForRoute("/ncr"),
      articles: retrieveArticles("ncr"),
    };
  }
  if (/calibrat|digital tape|arkit|lidar|tape measure|0\.15/.test(q.toLowerCase())) {
    return {
      source: "local",
      text: retrieveArticles("digital tape calibration arkit")[0]?.body
        + " Open Digital Tape from More or the sidebar. Calibrate this phone first. Browser is not ARKit.",
      tutorial: "qc",
      navigateTo: "/measure",
      highlights: walkForRoute("/measure"),
      articles: retrieveArticles("tape calibration"),
    };
  }
  if (/show me tension|tension tutorial|drape|hold-down/.test(q.toLowerCase())) {
    return {
      source: "local",
      text: retrieveArticles("tension twin L25390 hold-down")[0]?.body
        + " Open the tutorial Tension chapter, then Tension on the twin. Tap each strand. Tap each H-56-S.",
      tutorial: "tension",
      highlights: walkForRoute("/tension"),
      articles: retrieveArticles("tension twin"),
    };
  }
  const hits = retrieveArticles(q);
  const top = hits[0];
  const extra = hits.slice(1, 3).map((a) => a.title);
  const why = TUTORIAL_SECTIONS.find((s) => s.id === top?.tutorial)?.why;
  const text = [
    top?.body,
    why ? `Why this matters: ${why}` : "",
    extra.length ? `Also see: ${extra.join("; ")}.` : "",
    top?.tutorial ? `I can open the tutorial section “${top.tutorial}” if you want the long version.` : "",
  ].filter(Boolean).join("\n\n");
  return {
    source: "local",
    text: text || "Ask me about mill tags, tension, inspection, camber, finish, QR, or what to do when it goes wrong. I am a plant coach, not a generic chatbot.",
    tutorial: top?.tutorial || "what",
    highlights: walkForRoute(top?.route || route).slice(0, 2),
    articles: hits,
  };
}

export function groundedPayload(articles) {
  return (articles || []).slice(0, 6).map((a) => ({
    id: a.id,
    title: a.title,
    tutorial: a.tutorial,
    body: String(a.body || "").slice(0, 1200),
  }));
}
