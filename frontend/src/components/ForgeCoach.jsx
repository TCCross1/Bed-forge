import React, { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { BookOpen, Loader2, Mic, MicOff, Send, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useDevice } from "../context/DeviceContext";
import {
  AUDIT_PROMPTS, COACH_NAME, groundedPayload, localAnswer, suggestedPrompts, walkForRoute,
} from "../lib/forgeCoach";

function SpeechEngine() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function Overlay({ highlight, onNext, onClose, remaining }) {
  if (!highlight) return null;
  const pad = 6;
  const style = {
    top: Math.max(8, highlight.top - pad),
    left: Math.max(8, highlight.left - pad),
    width: highlight.width + pad * 2,
    height: highlight.height + pad * 2,
  };
  return (
    <div className="fixed inset-0 z-[70] pointer-events-none" data-testid="forge-coach-overlay">
      <div className="absolute inset-0 bg-black/45 pointer-events-auto" onClick={onClose} aria-hidden />
      <div
        className="absolute pointer-events-none rounded-none"
        style={{
          ...style,
          boxShadow: "0 0 0 2px #2979FF, 0 0 24px rgba(41,121,255,0.55)",
          border: "1px solid #C9A227",
        }}
      />
      <div
        className="absolute pointer-events-auto bg-[#0F1218]/95 backdrop-blur border border-[#1C2230] px-3 py-2 max-w-sm"
        style={{ top: Math.min(window.innerHeight - 96, style.top + style.height + 8), left: style.left }}
      >
        <div className="text-[10px] font-mono uppercase tracking-widest text-[#C9A227]">{COACH_NAME}</div>
        <div className="text-sm mt-1">{highlight.label}</div>
        <div className="flex gap-2 mt-2">
          {remaining > 0 && (
            <button type="button" onClick={onNext} className="min-h-12 px-3 bg-primary text-white text-xs font-semibold uppercase tracking-wider">
              Next
            </button>
          )}
          <button type="button" onClick={onClose} className="min-h-12 px-3 border border-[#1C2230] text-xs font-semibold uppercase tracking-wider">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

function measureTestId(testid) {
  const el = document.querySelector(`[data-testid="${testid}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return null;
  return { testid, top: r.top, left: r.left, width: r.width, height: r.height };
}

export default function ForgeCoach() {
  const { user } = useAuth();
  const device = useDevice();
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [messages, setMessages] = useState([]);
  const [queue, setQueue] = useState([]);
  const [highlight, setHighlight] = useState(null);
  const listRef = useRef(null);
  const recRef = useRef(null);

  const route = location.pathname || "/";
  const role = user?.role || "qc_tech";
  const prompts = suggestedPrompts(route, role);

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener("bf-coach-open", onOpen);
    return () => window.removeEventListener("bf-coach-open", onOpen);
  }, []);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, open]);

  const stopListen = () => {
    try {
      recRef.current?.stop?.();
    } catch (err) {
      console.error("[coach] speech stop", err);
    }
    recRef.current = null;
    setListening(false);
  };

  useEffect(() => () => stopListen(), []);

  const runHighlights = useCallback((steps) => {
    const list = (steps || []).filter((s) => s?.testid);
    setQueue(list);
    if (!list.length) {
      setHighlight(null);
      return;
    }
    const box = measureTestId(list[0].testid);
    setHighlight(box ? { ...list[0], ...box } : { ...list[0], top: 72, left: 16, width: 220, height: 48 });
  }, []);

  const nextHighlight = () => {
    const rest = queue.slice(1);
    setQueue(rest);
    if (!rest.length) {
      setHighlight(null);
      return;
    }
    const box = measureTestId(rest[0].testid);
    setHighlight(box ? { ...rest[0], ...box } : { ...rest[0], top: 72, left: 16, width: 220, height: 48 });
  };

  const openTutorial = (section) => {
    setOpen(false);
    setHighlight(null);
    navigate(section ? `/guide?section=${section}` : "/guide");
  };

  const ask = async (raw) => {
    const question = String(raw || draft || "").trim();
    if (!question) return;
    setDraft("");
    stopListen();
    const prior = { role: "user", text: question };
    setMessages((cur) => [...cur, prior]);
    const local = localAnswer(question, route, role);
    setBusy(true);
    try {
      const { data } = await api.post("/coach/ask", {
        question,
        route,
        role,
        grounded: groundedPayload(local.articles),
      });
      const text = (data && data.answer) || local.text;
      setMessages((cur) => [...cur, {
        role: "coach",
        text,
        tutorial: data?.tutorial || local.tutorial,
        source: data?.source || local.source,
      }]);
      if (local.navigateTo && local.navigateTo.split("?")[0] !== route.split("?")[0]) {
        navigate(local.navigateTo);
      }
      if (/walk me|this screen|show me tension/i.test(question)) {
        runHighlights(local.highlights?.length ? local.highlights : walkForRoute(route));
      }
    } catch (err) {
      console.error("[coach] ask failed", err);
      setMessages((cur) => [...cur, {
        role: "coach",
        text: local.text,
        tutorial: local.tutorial,
        source: "local",
      }]);
      if (err?.response?.status && err.response.status !== 401) {
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Coach used the on-device manual");
      }
      if (/walk me|this screen/i.test(question)) runHighlights(local.highlights);
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = () => {
    const Ctor = SpeechEngine();
    if (!Ctor) {
      toast.error("Voice is not available on this browser — type in the box");
      return;
    }
    if (listening) {
      stopListen();
      return;
    }
    try {
      const rec = new Ctor();
      rec.lang = "en-US";
      rec.interimResults = false;
      rec.onresult = (evt) => {
        const said = evt.results?.[0]?.[0]?.transcript || "";
        if (said) {
          setDraft(said);
          ask(said);
        }
      };
      rec.onerror = () => stopListen();
      rec.onend = () => setListening(false);
      recRef.current = rec;
      rec.start();
      setListening(true);
    } catch (err) {
      console.error("[coach] speech start", err);
      toast.error("Microphone unavailable — type the question");
      stopListen();
    }
  };

  if (!user) return null;

  const field = device.field;

  return (
    <>
      <Overlay
        highlight={highlight}
        remaining={Math.max(0, queue.length - 1)}
        onNext={nextHighlight}
        onClose={() => { setHighlight(null); setQueue([]); }}
      />

      {open && (
        <div className="fixed inset-0 z-[60] flex justify-end" data-testid="forge-coach-panel">
          <button type="button" className="flex-1 bg-black/50 backdrop-blur-[2px]" aria-label="Close Ask Expert" onClick={() => setOpen(false)} />
          <div
            className={`bg-[#0A0C10]/95 backdrop-blur-md border-l border-[#1C2230] flex flex-col ${
              field ? "w-full" : "w-full max-w-lg"
            }`}
            style={{ height: "100%", paddingBottom: "env(safe-area-inset-bottom)" }}
          >
            <div className="min-h-14 px-4 border-b border-[#1C2230] flex items-center justify-between gap-3">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">{COACH_NAME}</div>
                <div className="font-display font-bold uppercase tracking-wider text-sm">Product auditor + operator guide</div>
              </div>
              <button type="button" data-testid="forge-coach-close" onClick={() => setOpen(false)} className="min-h-12 min-w-12 border border-[#1C2230] flex items-center justify-center">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div ref={listRef} className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <div className="border border-[#1C2230] bg-[#0F1218] p-4">
                  <p className="text-sm leading-relaxed">
                    I score BedForge against the product contract — Blueprint Intelligence, Spec DNA, JOB SPECS, Open Job, QC, Batch Plant, Command Board. Ask what needs to be fixed. I cannot invent Spec numbers or override a gate.
                  </p>
                </div>
              )}
              {messages.map((msg, i) => (
                <div
                  key={`${msg.role}-${i}`}
                  className={`p-3 text-sm leading-relaxed ${
                    msg.role === "user" ? "border border-primary/40 bg-primary/10 ml-6" : "border border-[#1C2230] bg-[#0F1218] mr-4"
                  }`}
                >
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-1">
                    {msg.role === "user" ? "You" : COACH_NAME}
                    {msg.source === "llm" ? " · live" : msg.source === "audit" ? " · contract" : msg.role === "coach" ? " · plant manual" : ""}
                  </div>
                  <div className="whitespace-pre-wrap">{msg.text}</div>
                  {msg.tutorial && (
                    <button
                      type="button"
                      className="mt-3 min-h-12 px-3 border border-[#C9A227] text-[#C9A227] text-xs font-semibold uppercase tracking-wider flex items-center gap-2"
                      onClick={() => openTutorial(msg.tutorial)}
                      data-testid="coach-open-tutorial"
                    >
                      <BookOpen className="w-4 h-4" /> Show tutorial
                    </button>
                  )}
                </div>
              ))}
              {busy && (
                <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" /> Checking the contract and plant APIs…
                </div>
              )}
            </div>

            <div className="p-3 border-t border-[#1C2230] space-y-2">
              <div className="flex flex-wrap gap-2">
                {AUDIT_PROMPTS.map((p) => (
                  <button
                    key={`audit-${p}`}
                    type="button"
                    data-testid={`forge-coach-chip-${p.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-$/, "")}`}
                    onClick={() => ask(p)}
                    className="min-h-12 px-3 border border-[#C9A227]/70 text-[#C9A227] text-xs uppercase tracking-wider hover:border-[#C9A227] hover:bg-[#C9A227]/10"
                  >
                    {p}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {prompts.filter((p) => !AUDIT_PROMPTS.includes(p)).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => ask(p)}
                    className="min-h-12 px-3 border border-[#1C2230] text-xs uppercase tracking-wider hover:border-primary hover:text-primary"
                  >
                    {p}
                  </button>
                ))}
              </div>
              <form
                onSubmit={(e) => { e.preventDefault(); ask(draft); }}
                className="flex gap-2"
              >
                <input
                  data-testid="forge-coach-input"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Ask what needs to be fixed…"
                  className="flex-1 min-h-12 bg-[#0A0C10] border border-[#1C2230] px-3 text-sm"
                />
                <button type="button" onClick={toggleMic} className="min-h-12 min-w-12 border border-[#1C2230] flex items-center justify-center" aria-label="Voice input" data-testid="forge-coach-mic">
                  {listening ? <MicOff className="w-4 h-4 text-[#FFD600]" /> : <Mic className="w-4 h-4" />}
                </button>
                <button type="submit" disabled={busy} className="min-h-12 min-w-12 bg-primary text-white flex items-center justify-center" data-testid="forge-coach-send">
                  <Send className="w-4 h-4" />
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      <button
        type="button"
        data-testid="forge-coach-open"
        onClick={() => setOpen(true)}
        className={`fixed z-40 min-h-12 px-4 border border-[#C9A227] bg-[#0F1218]/90 backdrop-blur text-[#C9A227] font-semibold uppercase tracking-wider text-xs flex items-center gap-2 hover:bg-[#C9A227] hover:text-black ${
          field ? "right-3 bottom-20" : "right-6 bottom-6"
        }`}
        aria-label="Ask Expert"
      >
        <Sparkles className="w-4 h-4" /> Ask Expert
      </button>
    </>
  );
}
