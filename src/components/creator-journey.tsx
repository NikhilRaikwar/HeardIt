"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, AudioLines, Check, ClipboardCheck, Copy, FileText, Headphones, LoaderCircle, PencilLine, RefreshCw, Share2, Sparkles, Volume2 } from "lucide-react";
import { track } from "@/components/heardit";

type OptionDraft = { label: string; description: string };
type AudioAsset = { audio_id: string; url: string; cached: boolean; model: string; direction: string; voice: string; created_at: string };
type Draft = { sentence: string; options: [OptionDraft, OptionDraft, OptionDraft, OptionDraft]; direction: string; audio: AudioAsset | null; step: 1 | 2 | 3 };
type Suggestion = { intended_label: string; alternative_labels: [string, string, string]; fish_direction: string; explanation: string };
type Published = { id: string; management_token: string; status: string };
type ApiFailure = { error?: { message?: string }; detail?: string };

const DRAFT_KEY = "heardit-creator-draft-v2";
const defaults: Draft = {
  sentence: "I thought you said you’d be here by now.",
  options: [
    { label: "Curious", description: "Genuinely wondering" },
    { label: "Annoyed", description: "Slightly frustrated" },
    { label: "Hurt", description: "Feeling upset" },
    { label: "Playful", description: "Light and teasing" },
  ],
  direction: "[curious, slightly surprised, gentle tone]",
  audio: null,
  step: 1,
};

async function api<T,>(path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: body ? "POST" : "GET",
    headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  let data: unknown;
  try { data = await response.json(); }
  catch { throw new Error(`HeardIt API returned an unexpected response (HTTP ${response.status}). Check that the FastAPI service is running and reachable.`); }
  if (!response.ok) {
    const failure = data as ApiFailure;
    throw new Error(failure.error?.message || failure.detail || `HeardIt API request failed (HTTP ${response.status}).`);
  }
  return data as T;
}

function Wordmark() {
  return <Link href="/" className="hi-wordmark" aria-label="HeardIt home"><span className="hi-mark"><AudioLines size={18}/></span><span>heard<span>it</span></span></Link>;
}

function JourneyHeader() {
  return <header className="hi-landing-nav"><div className="hi-landing-nav-inner"><Wordmark/><Link href="/" className="hj-exit">Back to HeardIt</Link></div></header>;
}

function CreatorProgress({ step, onStep }: { step: 1 | 2 | 3 | 4; onStep: (step: 1 | 2 | 3) => void }) {
  const labels = ["Write", "Generate", "Review", "Share"];
  return <ol className="hj-progress" aria-label={`Step ${step} of 4`}>
      {labels.map((label, index) => {
        const number = index + 1;
        const reached = number <= step;
        return <li key={label} className={`${number === step ? "is-active" : ""} ${number < step ? "is-complete" : ""}`}>
          {number < 4 && <span className="hj-progress-line"/>}
          <button type="button" onClick={() => number < step && number <= 3 && onStep(number as 1 | 2 | 3)} disabled={!reached || number === step || number === 4} aria-current={number === step ? "step" : undefined}>
            <span className="hj-progress-dot">{number < step ? <Check size={14}/> : number}</span><b>{label}</b>
          </button>
        </li>;
      })}
    </ol>;
}

function AudioPreview({ audio }: { audio: AudioAsset }) {
  const [failed, setFailed] = useState(false);
  return <div className="hj-audio-preview">
    <div className="hj-audio-icon"><Volume2 size={19}/></div>
    <audio controls preload="metadata" src={audio.url} aria-label="Generated Fish Audio clip" onError={() => setFailed(true)} onPlay={() => track("audio_played", { surface: "creator_preview" })}/>
    {failed && <span className="hj-audio-error" role="alert">This saved audio could not be loaded.</span>}
  </div>;
}

function ListenerPreview({ draft, audio, mode, onMode }: { draft: Draft; audio: AudioAsset | null; mode: "audio" | "text"; onMode: (mode: "audio" | "text") => void }) {
  const [choice, setChoice] = useState("");
  return <aside className="hi-live-preview hj-live-preview" aria-label="Live listener preview">
    <div className="hi-preview-head"><div><b>LIVE PREVIEW</b><span>How your test will appear to listeners</span></div><div className="hi-preview-tabs" role="group" aria-label="Preview condition">
      <button type="button" className={mode === "audio" ? "is-active" : ""} aria-pressed={mode === "audio"} onClick={() => { onMode("audio"); setChoice(""); }}><Headphones size={15}/>Audio test</button>
      <button type="button" className={mode === "text" ? "is-active" : ""} aria-pressed={mode === "text"} onClick={() => { onMode("text"); setChoice(""); }}><FileText size={15}/>Text test</button>
    </div></div>
    <div className="hi-preview-stage"><div className="hi-preview-phone hj-preview-phone">
      <div className="hi-phone-top"><span>1 / 1</span><span className="hi-phone-dot"/></div>
      <h2>{mode === "audio" ? "Listen and choose what you think it means." : "Read the words and choose what you think they mean."}</h2>
      {mode === "audio" ? audio ? <div className="hi-phone-audio"><audio controls preload="metadata" src={audio.url} aria-label="Creator preview audio"/></div> : <div className="hi-phone-audio-empty"><span className="hi-phone-audio-icon"><Headphones size={16}/></span><span>Generate audio to preview it here.</span></div> : <blockquote className="hi-phone-sentence">{draft.sentence || "Your sentence will appear here."}</blockquote>}
      <div className="hi-preview-options">{draft.options.map(option => <button type="button" key={option.label} className={choice === option.label ? "is-selected" : ""} onClick={() => setChoice(option.label)}><span>{choice === option.label ? <Check size={12}/> : null}</span>{option.label || "Answer choice"}</button>)}</div>
      <button className="hi-phone-submit" type="button" disabled>Submit answer</button><p className="hi-phone-note">Preview only. This does not count as a response.</p>
    </div></div>
    <div className="hi-preview-footer"><span><Sparkles size={15}/></span><div><b>What listeners will see</b><p>Each visitor is randomly assigned to hear the voice or read the exact same sentence. Their answer is saved before the intended meaning is revealed.</p></div></div>
  </aside>;
}

export function CreatorJourney() {
  const router = useRouter();
  const publishAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const [draft, setDraft] = useState<Draft>(defaults);
  const [hydrated, setHydrated] = useState(false);
  const [busy, setBusy] = useState<"suggest" | "direction" | "generate" | "publish" | "">("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [previewMode, setPreviewMode] = useState<"audio" | "text">("audio");
  const [labelsTouched, setLabelsTouched] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(DRAFT_KEY);
      if (stored) {
        const value = JSON.parse(stored) as Partial<Draft>;
        setDraft({ ...defaults, ...value, options: Array.isArray(value.options) && value.options.length === 4 ? value.options as Draft["options"] : defaults.options });
      }
    } catch { localStorage.removeItem(DRAFT_KEY); }
    setHydrated(true);
  }, []);

  useEffect(() => { if (hydrated) localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); }, [draft, hydrated]);
  useEffect(() => { track("create_started", { surface: "creator_journey" }); }, []);

  const uniqueLabels = useMemo(() => {
    const labels = draft.options.map(option => option.label.trim().toLocaleLowerCase());
    return labels.every(Boolean) && new Set(labels).size === 4;
  }, [draft.options]);
  const sentenceValid = draft.sentence.trim().length > 0 && draft.sentence.length <= 180 && !/[\r\n]/.test(draft.sentence.trim());
  const canGenerate = sentenceValid && uniqueLabels && draft.direction.trim().length > 0 && draft.direction.length <= 120 && !busy;

  function update(patch: Partial<Draft>) { setDraft(current => ({ ...current, ...patch })); }
  function updateSentence(sentence: string) { update({ sentence, audio: null, step: 1 }); setError(""); setNotice(""); }
  function updateDirection(direction: string) { update({ direction, audio: null, step: 1 }); setError(""); setNotice(""); }
  function updateOption(index: number, key: keyof OptionDraft, value: string) {
    setDraft(current => ({ ...current, options: current.options.map((option, i) => i === index ? { ...option, [key]: value } : option) as Draft["options"] }));
    setLabelsTouched(true); setError(""); setNotice("");
  }

  async function suggest(mode: "all" | "direction") {
    if (!sentenceValid) { setError("Enter one sentence of up to 180 characters first."); return; }
    setError(""); setNotice(""); setBusy(mode === "all" ? "suggest" : "direction");
    track("ai_suggestion_requested", { surface: mode === "all" ? "interpretations" : "direction" });
    try {
      const result = await api<Suggestion>("/suggestions", { sentence: draft.sentence.trim(), intended_label: draft.options[0].label.trim() || undefined });
      if (mode === "direction") { updateDirection(result.fish_direction); setNotice("Direction suggestion is ready. Review and edit it before generating."); }
      else {
        setDraft(current => ({ ...current, options: [{ ...current.options[0], label: result.intended_label }, ...result.alternative_labels.map((label, i) => ({ ...current.options[i + 1], label }))] as Draft["options"], direction: result.fish_direction, audio: null, step: 1 }));
        setLabelsTouched(true); setNotice("Suggestions are ready. Review and edit each one before generating.");
      }
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }

  async function generate() {
    setError(""); setNotice(""); setLabelsTouched(true);
    if (!sentenceValid) { setError("Enter one sentence of up to 180 characters."); return; }
    if (!uniqueLabels) { setError("Enter four distinct, non-empty interpretations before generating."); return; }
    if (!draft.direction.trim()) { setError("Add a Fish Audio direction before generating."); return; }
    setBusy("generate"); track("voice_generation_started", { model: "s2.1-pro-free" });
    try {
      const result = await api<AudioAsset>("/audio/generate", { sentence: draft.sentence.trim(), direction: draft.direction.trim() });
      setDraft(current => ({ ...current, audio: { ...result, url: result.url.startsWith("http") ? result.url : result.url || `/api/v1/audio/${result.audio_id}` }, step: 2 }));
      track("voice_generation_completed", { cached: result.cached, model: result.model });
    } catch (reason) { setError((reason as Error).message); track("voice_generation_failed"); }
    finally { setBusy(""); }
  }

  function continueToReview() {
    if (!draft.audio) { setError("Generate and save audio before reviewing the test."); return; }
    if (!uniqueLabels) { setDraft(current => ({ ...current, step: 1 })); setError("Your four interpretations must be distinct. Review them before publishing."); return; }
    setError(""); setDraft(current => ({ ...current, step: 3 })); track("review_opened");
  }

  async function publish() {
    if (!draft.audio) { setError("Generate and save audio before publishing."); return; }
    setBusy("publish"); setError("");
    try {
      const body = {
        sentence: draft.sentence.trim(), intended_label: draft.options[0].label.trim(),
        distractors: draft.options.slice(1).map(option => option.label.trim()),
        option_descriptions: draft.options.map(option => option.description.trim()),
        direction: draft.direction.trim(), audio_id: draft.audio.audio_id,
      };
      const fingerprint = JSON.stringify(body);
      if (!publishAttempt.current || publishAttempt.current.fingerprint !== fingerprint) {
        let saved: { fingerprint?: string; key?: string } | null = null;
        try { saved = JSON.parse(sessionStorage.getItem("heardit-publish-attempt-v1") || "null") as { fingerprint?: string; key?: string } | null; } catch {}
        const key = saved?.fingerprint === fingerprint && typeof saved.key === "string" ? saved.key : crypto.randomUUID();
        publishAttempt.current = { fingerprint, key };
        sessionStorage.setItem("heardit-publish-attempt-v1", JSON.stringify(publishAttempt.current));
      }
      const result = await api<Published>("/tests", body, { "Idempotency-Key": publishAttempt.current.key });
      localStorage.setItem(`heardit-owner-${result.id}`, result.management_token);
      localStorage.setItem(`heardit-owner-id-${result.id}`, "1");
      localStorage.removeItem(DRAFT_KEY);
      sessionStorage.removeItem("heardit-publish-attempt-v1");
      track("test_published", { test_id: result.id });
      router.push(`/created/${result.id}`);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }

  const stage = draft.step;
  return <div className="hi-landing hj-shell">
    <JourneyHeader/>
    <main className="hj-main">
      <div className="hj-page-heading"><div className="hj-heading-copy"><span className="hi-small-label">CREATOR STUDIO</span><h1>{stage === 1 ? "Create a listening test" : stage === 2 ? "Your voice is ready" : "Review your test"}</h1><p>{stage === 1 ? "Turn one sentence into a question people can answer." : stage === 2 ? "Listen to the generated audio before you move on." : "Make sure the sentence, interpretations and voice direction are ready."}</p></div><CreatorProgress step={stage} onStep={next => { setError(""); update({ step: next }); }}/>{stage > 1 && <button className="hj-back-step" type="button" onClick={() => { setError(""); update({ step: stage === 3 ? 2 : 1 }); }}><ArrowLeft size={15}/>Back</button>}</div>

      {stage === 1 && <div className="hi-studio-layout hj-layout">
        <section className="hi-studio-form hj-form" aria-label="Listening test setup">
          <section className="hi-studio-section"><div className="hi-studio-section-heading"><span className="hi-studio-number">1</span><div><h2>Your sentence</h2><p>Enter one short sentence (up to 180 characters).</p></div><small className="hi-studio-count">{draft.sentence.length}/180</small></div><textarea id="sentence" aria-label="Your sentence" maxLength={180} value={draft.sentence} onChange={event => updateSentence(event.target.value)} placeholder="I thought you said you’d be here by now." rows={3}/>{!sentenceValid && draft.sentence.length > 0 && <p className="hj-inline-error">Use one sentence on a single line.</p>}</section>
          <section className="hi-studio-section"><div className="hi-studio-section-heading"><span className="hi-studio-number">2</span><div><h2>What do you intend?</h2><p>Choose the intended meaning and three plausible alternatives.</p></div><button className="hi-quiet-button" type="button" onClick={() => void suggest("all")} disabled={!sentenceValid || !!busy}><Sparkles size={15}/>{busy === "suggest" ? <><LoaderCircle className="hi-spin" size={14}/>Thinking</> : "AI suggest"}</button></div><div className="hi-meaning-grid">{draft.options.map((option, index) => <label className={`hi-meaning-card ${index === 0 ? "is-intended" : ""}`} key={index}><span className="hi-meaning-indicator">{index === 0 ? <Check size={13}/> : null}</span><span className="hi-meaning-meta">{index === 0 ? "Your intended meaning" : `Alternative ${index}`}</span><input aria-label={index === 0 ? "Intended interpretation" : `Alternative ${index}`} value={option.label} onChange={event => updateOption(index, "label", event.target.value)} placeholder={index === 0 ? "e.g. Curious" : "e.g. Annoyed"} maxLength={60}/><input className="hj-description-input" aria-label={`${index === 0 ? "Intended" : `Alternative ${index}`} description`} value={option.description} onChange={event => updateOption(index, "description", event.target.value)} placeholder="Add a short description" maxLength={120}/></label>)}</div>{labelsTouched && !uniqueLabels && <p className="hj-inline-error">All four labels must be distinct and non-empty.</p>}</section>
          <section className="hi-studio-section"><div className="hi-studio-section-heading"><span className="hi-studio-number">3</span><div><h2>Fish inline direction</h2><p>Add a voice direction. Review it before synthesis.</p></div><button className="hi-quiet-button" type="button" onClick={() => void suggest("direction")} disabled={!sentenceValid || !!busy}><Sparkles size={15}/>{busy === "direction" ? "Improving" : "Improve with AI"}</button></div><input id="direction" className="hi-direction-input" aria-label="Fish inline direction" value={draft.direction} onChange={event => updateDirection(event.target.value)} placeholder="[curious, slightly surprised, gentle tone]" maxLength={120}/><div className="hi-examples"><span className="hi-examples-icon"><AudioLines size={15}/></span><div><b>Example directions</b><div>{["[warm, friendly]", "[sad, emotional]", "[annoyed, frustrated]", "[playful, teasing]"].map(example => <button type="button" key={example} onClick={() => updateDirection(example)}>{example}</button>)}</div></div></div><p className="hj-direction-note">Direction cues are instructions to try. They do not guarantee a particular performance.</p></section>
          <section className="hi-studio-section hi-generate-section"><div className="hi-studio-section-heading"><span className="hi-studio-number">4</span><div><h2>Generate voice</h2><p>Create one real expressive clip with Fish Audio.</p></div></div><button className="hi-button hi-generate" type="button" onClick={() => void generate()} disabled={!canGenerate}>{busy === "generate" ? <><LoaderCircle className="hi-spin" size={16}/>Generating with Fish Audio…</> : <><AudioLines size={17}/>{draft.audio ? "Generate voice again" : "Generate voice"}<ArrowRight size={16}/></>}</button><p className="hi-generation-note"><AudioLines size={13}/>{draft.audio ? `Last saved clip: ${draft.audio.model}${draft.audio.cached ? " · reused from cache" : ""}.` : "Uses Fish Audio s2.1-pro-free. Audio must save before review."}</p></section>
          {error && <div className="hi-error" role="alert">{error}</div>}{notice && <p className="hj-notice" role="status"><Check size={14}/>{notice}</p>}
        </section>
        <ListenerPreview draft={draft} audio={draft.audio} mode={previewMode} onMode={setPreviewMode}/>
      </div>}

      {stage === 2 && <section className="hj-stage-card">
        <div className="hj-stage-sentence"><span>YOUR SENTENCE</span><blockquote>“{draft.sentence}”</blockquote></div>
        {draft.audio ? <AudioPreview key={draft.audio.audio_id} audio={draft.audio}/> : <div className="hj-stage-empty"><Headphones size={20}/><p>No saved clip yet.</p><button className="hi-button" onClick={() => update({ step: 1 })}>Return to writing</button></div>}
        {draft.audio && <div className="hj-generation-details"><div className="hj-details-heading"><span className="hj-icon-disc"><AudioLines size={16}/></span><div><b>Generation details</b><small>Provider metadata for this saved clip</small></div></div><dl><div><dt>Model</dt><dd>{draft.audio.model}</dd></div><div><dt>Direction</dt><dd>{draft.audio.direction}</dd></div><div><dt>Voice</dt><dd>{draft.audio.voice}</dd></div><div><dt>Created</dt><dd>{new Date(draft.audio.created_at).toLocaleString()}</dd></div><div><dt>Audio asset</dt><dd>{draft.audio.audio_id}</dd></div></dl>{draft.audio.cached && <p className="hj-cache-note"><Check size={14}/>This request matched an existing saved clip; no new synthesis was made.</p>}</div>}
        {error && <div className="hi-error" role="alert">{error}</div>}
        <div className="hj-stage-actions"><button className="hj-secondary-button" type="button" onClick={() => void generate()} disabled={!!busy}><RefreshCw size={15}/>{busy === "generate" ? "Generating…" : "Regenerate"}</button><button className="hi-button" type="button" onClick={continueToReview} disabled={!draft.audio}>Continue to review <ArrowRight size={16}/></button></div>
      </section>}

      {stage === 3 && <div className="hj-review-layout"><section className="hj-review-card">
        <div className="hj-review-title"><span className="hj-icon-disc"><ClipboardCheck size={17}/></span><div><span className="hi-small-label">FINAL CHECK</span><h2>Your listening test</h2></div></div>
        <div className="hj-review-row"><div><span>Sentence</span><p>{draft.sentence}</p></div><button type="button" onClick={() => update({ step: 1 })}>Edit</button></div>
        <div className="hj-review-row"><div><span>Intended meaning</span><p><b>{draft.options[0].label}</b><small>{draft.options[0].description}</small></p></div><button type="button" onClick={() => update({ step: 1 })}>Edit</button></div>
        <div className="hj-review-row"><div><span>Alternative meanings</span><div className="hj-review-options">{draft.options.slice(1).map(option => <span key={option.label}><i/>{option.label}<small>{option.description}</small></span>)}</div></div><button type="button" onClick={() => update({ step: 1 })}>Edit</button></div>
        <div className="hj-review-row"><div><span>Fish direction</span><p className="hj-direction-review">{draft.direction}</p></div><button type="button" onClick={() => update({ step: 1 })}>Edit</button></div>
        {draft.audio && <div className="hj-review-audio"><span>VOICE PREVIEW</span><AudioPreview audio={draft.audio}/><small>{draft.audio.model} · {draft.audio.cached ? "Cached audio" : "Generated audio"}</small></div>}
        {error && <div className="hi-error" role="alert">{error}</div>}
        <button className="hi-button hj-publish-button" type="button" onClick={() => void publish()} disabled={!draft.audio || !uniqueLabels || !!busy}>{busy === "publish" ? <><LoaderCircle className="hi-spin" size={16}/>Publishing your test…</> : <>Publish test <ArrowRight size={16}/></>}</button>
      </section><aside className="hj-review-aside"><ListenerPreview draft={draft} audio={draft.audio} mode={previewMode} onMode={setPreviewMode}/><div className="hj-how-it-works"><b>How this works</b><p><Check size={14}/>Listeners are randomly assigned to audio or text.</p><p><Check size={14}/>They choose one of the same four meanings.</p><p><Check size={14}/>You see both groups after responses arrive.</p></div></aside></div>}
    </main>
  </div>;
}

type CreatorData = { id: string; sentence: string; intended_label: string; distractors: string[]; direction: string; model: string; audio_id: string; created_at: string; status: string };

export function CreatedPage({ id }: { id: string }) {
  const [data, setData] = useState<CreatorData | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const url = typeof window === "undefined" ? "" : `${window.location.origin}/t/${id}`;
  useEffect(() => {
    track("share_page_viewed", { test_id: id });
    const token = localStorage.getItem(`heardit-owner-${id}`);
    if (!token) { setError("Creator access is saved on the device that published this test. This browser does not have that private access."); setLoading(false); return; }
    api<CreatorData>(`/tests/${id}/creator`, undefined, { "X-Management-Token": token }).then(setData).catch(reason => setError((reason as Error).message)).finally(() => setLoading(false));
  }, [id]);
  async function copy() {
    try { await navigator.clipboard.writeText(url); setCopied(true); track("share_clicked", { surface: "created_page", test_id: id }); window.setTimeout(() => setCopied(false), 1800); }
    catch { setError("Clipboard access is unavailable. Copy the test link from the address below."); }
  }
  const shareText = encodeURIComponent("Can you hear what this voice really means?");
  const shareUrl = encodeURIComponent(url);
  if (loading) return <div className="hi-landing"><StudioNav/><main className="hj-created"><LoaderCircle className="hi-spin"/>Loading your test…</main></div>;
  return <div className="hi-landing hj-shell"><StudioNav/><div className="hj-share-progress"><CreatorProgress step={4} onStep={() => undefined}/></div><main className="hj-created">
    <span className="hj-success-icon"><Check size={25}/></span><span className="hi-small-label">TEST PUBLISHED</span><h1>Your test is live.</h1><p className="hj-created-subtitle">Share the listening test to collect real responses.</p>
    {error && <div className="hi-error" role="alert">{error}</div>}
    {data && <>
      <div className="hj-share-card"><span>PUBLIC LISTENING LINK</span><div><code>{url}</code><button type="button" className="hi-button" onClick={() => void copy()}>{copied ? <Check size={16}/> : <Copy size={16}/ >}{copied ? "Copied" : "Copy link"}</button></div></div>
      <div className="hj-social-share"><a href={`https://twitter.com/intent/tweet?text=${shareText}&url=${shareUrl}`} target="_blank" rel="noreferrer">Share on X <ArrowRight size={13}/></a><a href={`https://www.linkedin.com/sharing/share-offsite/?url=${shareUrl}`} target="_blank" rel="noreferrer">LinkedIn <ArrowRight size={13}/></a><a href={`https://wa.me/?text=${shareText}%20${shareUrl}`} target="_blank" rel="noreferrer">WhatsApp <ArrowRight size={13}/></a><a href={`https://www.reddit.com/submit?url=${shareUrl}&title=${shareText}`} target="_blank" rel="noreferrer">Reddit <ArrowRight size={13}/></a>{typeof navigator !== "undefined" && "share" in navigator && <button type="button" onClick={() => void navigator.share({ title: "HeardIt listening test", text: "Can you hear what this voice really means?", url })}><Share2 size={13}/>More options</button>}</div>
      <div className="hj-created-actions"><Link className="hi-button" href={`/r/${id}`}>View results <ArrowRight size={16}/></Link><Link className="hj-secondary-button" href={`/t/${id}`}>Open listening test <ArrowRight size={15}/></Link></div>
      <p className="hj-private-note"><span><PencilLine size={14}/></span>Your private results access is stored in this browser. Save the results page link on this device; clearing browser data can remove access.</p>
      <p className="hj-created-meta">{data.model} · created {new Date(data.created_at).toLocaleString()}</p>
    </>}
    {!data && <p className="hj-private-note">Open this page on the device where you created the test. The private management token is never part of its public link.</p>}
    <Link className="hj-home-link" href="/create">Create another test <ArrowRight size={14}/></Link>
  </main></div>;
}

function StudioNav() {
  return <header className="hi-landing-nav"><div className="hi-landing-nav-inner"><Wordmark/><Link href="/create" className="hi-nav-cta">Creator studio <ArrowRight size={14}/></Link></div></header>;
}
