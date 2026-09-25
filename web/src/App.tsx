import { useEffect, useMemo, useRef, useState, type ChangeEvent, type PointerEvent as ReactPointerEvent, type ReactNode, type RefObject } from "react";
import {
  composePrompt,
  deleteTrack,
  generate,
  loadBootstrap,
  loadOptions,
  loadState,
  moveJob,
  rateTrack,
  remix,
  removeJob,
  undoDelete,
  type Bootstrap,
  type Job,
  type ModelInfo,
  type Pending,
  type Track,
} from "./api";
import { nextDrawer, snapDrawer, type DrawerMode } from "./drawer";
import { bindExclusivePlayback } from "./playback";

type Notice = { tone: "ok" | "error"; text: string } | null;

function selectedValues(event: ChangeEvent<HTMLSelectElement>) {
  return Array.from(event.target.selectedOptions).map((option) => option.value);
}

function formatSeconds(value: number | null) {
  if (value == null || !Number.isFinite(value)) return null;
  return Number.isInteger(value) ? `${value}s` : `${value.toFixed(1)}s`;
}

function formatClock(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function clampControl(control: ModelInfo["duration"], current: number) {
  let value = Number.isFinite(current) ? current : control.default;
  value = Math.max(control.minimum, value);
  if (control.maximum != null) value = Math.min(control.maximum, value);
  return control.integer ? Math.round(value) : value;
}

export function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [modelName, setModelName] = useState("");
  const [genre, setGenre] = useState("");
  const [bpm, setBpm] = useState(120);
  const [mood, setMood] = useState("");
  const [moods, setMoods] = useState<string[]>([]);
  const [instruments, setInstruments] = useState<string[]>([]);
  const [instrumentChoices, setInstrumentChoices] = useState<string[]>([]);
  const [character, setCharacter] = useState<string[]>([]);
  const [keywords, setKeywords] = useState("");
  const [vocals, setVocals] = useState("Instrumental");
  const [lyrics, setLyrics] = useState("");
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(180);
  const [steps, setSteps] = useState(8);
  const [guidance, setGuidance] = useState(1);
  const [seed, setSeed] = useState(42);
  const [useSeed, setUseSeed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [queue, setQueue] = useState<Job[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const [signature, setSignature] = useState("");
  const [filterGenre, setFilterGenre] = useState("any");
  const [filterRating, setFilterRating] = useState("any");
  const [filterQuery, setFilterQuery] = useState("");
  const [remixTrack, setRemixTrack] = useState("");
  const [remixFile, setRemixFile] = useState<File | null>(null);
  const [remixPrompt, setRemixPrompt] = useState("");
  const [remixNoise, setRemixNoise] = useState(0.6);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tool, setTool] = useState<"generate" | "remix">("generate");
  const [drawer, setDrawer] = useState<DrawerMode>("closed");
  const followQueue = useRef(true);
  const draggingDrawer = useRef(false);
  const seenFailures = useRef(new Set<string>());

  const model = useMemo(
    () => bootstrap?.models.find((item) => item.name === modelName) ?? null,
    [bootstrap, modelName],
  );

  useEffect(() => {
    loadBootstrap().then((data) => {
      const initial = data.models.find((item) => item.name === data.default_model) ?? data.models[0];
      setBootstrap(data);
      setModelName(initial.name);
      setMood(data.mood_default);
      setMoods([data.mood_default]);
      setDuration(initial.duration.default);
      if (initial.steps) setSteps(initial.steps.default);
      if (initial.guidance) setGuidance(initial.guidance.default);
      setVocals(initial.voice_choices[0] ?? "Instrumental");
    }).catch((error: Error) => setNotice({ tone: "error", text: error.message }));
  }, []);

  useEffect(() => {
    let timer = 0;
    const pull = () => {
      loadState(signature).then((state) => {
        setQueue(state.queue);
        setPending(state.pending);
        setSignature(state.signature);
        if (state.tracks) setTracks(state.tracks);
      }).catch(() => undefined);
    };
    pull();
    timer = window.setInterval(pull, 1000);
    return () => window.clearInterval(timer);
  }, [signature]);

  function applyModel(nextName: string) {
    const next = bootstrap?.models.find((item) => item.name === nextName);
    if (!next) return;
    const vocal = next.voice_choices.includes(vocals)
      ? vocals
      : vocals === "Instrumental"
        ? next.voice_choices[0]
        : next.voice_choices[1] ?? next.voice_choices[0];
    setModelName(next.name);
    setDuration(clampControl(next.duration, duration));
    if (next.steps) setSteps(next.steps.default);
    if (next.guidance) setGuidance(next.guidance.default);
    setVocals(vocal);
  }

  async function writePrompt(nextGenre: string, nextMood = mood) {
    if (!nextGenre || !model) {
      setPrompt("");
      return;
    }
    const result = await composePrompt({
      genre: nextGenre,
      model: model.name,
      bpm,
      mood: nextMood,
      vocals,
      instruments,
      character,
      keywords,
    });
    setPrompt(result.prompt);
  }

  async function onGenre(next: string) {
    setGenre(next);
    setInstruments([]);
    if (!next) {
      setPrompt("");
      return;
    }
    const options = await loadOptions(next);
    setMoods(options.moods);
    setInstrumentChoices(options.instruments);
    setMood(options.moods[0] ?? "");
    if (options.bpm) setBpm(options.bpm);
    if (model) {
      setDuration(clampControl(model.duration, options.duration ?? model.duration.default));
    }
    const result = await composePrompt({
      genre: next,
      model: modelName,
      bpm: options.bpm ?? bpm,
      mood: options.moods[0],
      vocals,
      instruments: [],
      character,
      keywords,
    });
    setPrompt(result.prompt);
  }

  async function onGenerate() {
    if (!model) return;
    setBusy(true);
    setNotice(null);
    try {
      const result = await generate({
        model: model.name,
        prompt,
        duration,
        steps: model.steps ? steps : null,
        guidance: model.guidance ? guidance : null,
        seed,
        use_seed: useSeed,
        lyrics: model.supports_lyrics && vocals !== "Instrumental" ? lyrics : null,
        genre: genre || null,
      });
      setSeed(result.seed);
      followQueue.current = true;
      setQueue(result.queue);
      setNotice({ tone: "ok", text: "Queued. You can set up another one." });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Could not queue" });
    } finally {
      setBusy(false);
    }
  }

  async function onRemix() {
    if (!model) return;
    setBusy(true);
    setNotice(null);
    try {
      const shared = {
        model: model.name,
        prompt: remixPrompt,
        noise: remixNoise,
        steps: model.steps ? steps : null,
        guidance: model.guidance ? guidance : null,
      };
      const result = remixFile
        ? await remix(remixForm(shared, remixFile))
        : await remix({ ...shared, track: remixTrack });
      followQueue.current = true;
      setQueue(result.queue);
      setNotice({ tone: "ok", text: "Remix queued." });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Could not remix" });
    } finally {
      setBusy(false);
    }
  }

  const visibleTracks = tracks.filter((track) => {
    if (filterGenre !== "any" && (track.genre ?? "") !== filterGenre) return false;
    if (filterRating === "unrated" && track.rating) return false;
    if (filterRating === "keep" || filterRating === "discard") {
      if (track.rating !== filterRating) return false;
    }
    const needle = filterQuery.trim().toLowerCase();
    if (!needle) return true;
    const haystack = `${track.title} ${track.prompt} ${track.name}`.toLowerCase();
    return haystack.includes(needle);
  });

  const genreFilters = ["any", ...new Set(
    tracks.map((track) => track.genre).filter((value): value is string => Boolean(value)),
  )];
  const activeCount = queue.filter((job) => job.status === "running" || job.status === "queued").length;
  const focusJob = queue.find((job) => job.status === "running")
    ?? queue.find((job) => job.status === "queued")
    ?? null;

  useEffect(() => {
    if (draggingDrawer.current) return;
    setDrawer((current) => nextDrawer(current, followQueue.current, activeCount));
  }, [activeCount]);

  useEffect(() => {
    for (const job of queue) {
      if (job.status !== "failed" || !job.error || seenFailures.current.has(job.id)) continue;
      seenFailures.current.add(job.id);
      setNotice({ tone: "error", text: job.error });
    }
  }, [queue]);

  function settleDrawer(next: DrawerMode) {
    followQueue.current = next !== "closed";
    setDrawer(next);
  }

  if (!bootstrap || !model) {
    return <p className="p-8 text-[var(--muted)]">Loading the workbench.</p>;
  }

  return (
    <div className={`app-shell${drawer === "peek" ? " drawer-is-peek" : ""}`}>
      <header className="page-header">
        <div className="tool-tabs" role="tablist" aria-label="Tools">
          <button type="button" role="tab" aria-selected={tool === "generate"} className={tool === "generate" ? "is-selected" : ""} onClick={() => setTool("generate")}>Generate</button>
          <button type="button" role="tab" aria-selected={tool === "remix"} className={tool === "remix" ? "is-selected" : ""} onClick={() => setTool("remix")}>Remix</button>
        </div>
        <label className="model-picker" title={`${model.model_id}. ${model.available ? "Ready" : "Setup missing"}. ${model.licence}. Max ${Math.round(model.max_duration)}s. ${model.notes}`}>
          <span className="model-picker-word">Model</span>
          <select aria-label="Model" value={modelName} onChange={(event) => applyModel(event.target.value)}>
            {bootstrap.models.map((item) => (
              <option key={item.name} value={item.name}>{item.name}</option>
            ))}
          </select>
          <svg className="model-chevron" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2.2 4.4 6 8l3.8-3.6" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </label>
      </header>

      <section id="controls-panel">
        {tool === "generate" ? (
        <>
        <label>
          <span className="field-label">Genre</span>
          <select value={genre} onChange={(event) => void onGenre(event.target.value)}>
            <option value="">Choose a genre</option>
            {bootstrap.genres.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label title="Written into the prompt. The model has no tempo control.">
            <span className="field-label">{bpm} BPM</span>
            <input type="range" min={50} max={200} step={1} value={bpm} onChange={(event) => setBpm(Number(event.target.value))} />
          </label>
          <label>
            <span className="field-label">Mood</span>
            <select value={mood} onChange={(event) => setMood(event.target.value)}>
              {moods.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" title={model.voice_info}>
          {model.voice_choices.map((choice) => (
            <button
              key={choice}
              type="button"
              onClick={() => setVocals(choice)}
              className={`voice-choice ${vocals === choice ? "is-selected" : ""}`}
            >
              {choice}
            </button>
          ))}
        </div>

        <div className="prompt-block">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="field-label">Prompt</span>
            <button type="button" className="rounded-full border border-[var(--line)] px-2.5 py-0.5 text-xs" onClick={() => void writePrompt(genre).catch((error: Error) => setNotice({ tone: "error", text: error.message }))}>Regenerate</button>
          </div>
          <textarea
            value={prompt}
            title={model.prompt_hint}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Edit the prompt"
          />
        </div>

        {model.supports_lyrics && vocals !== "Instrumental" ? (
          <textarea className="lyrics-field" aria-label="Lyrics" value={lyrics} onChange={(event) => setLyrics(event.target.value)} placeholder="Lyrics" />
        ) : null}

        <div className="duration-row">
          <Slider
            wide
            format={formatClock}
            label="Duration"
            hint={`${model.duration.label}. ${model.duration.info}`}
            control={model.duration}
            value={duration}
            onChange={setDuration}
          />
          <button
            type="button"
            className="settings-toggle"
            aria-label="Generation settings"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((open) => !open)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
              <path d="M12 3.2v2.3M12 18.5v2.3M3.2 12h2.3M18.5 12h2.3M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        {settingsOpen ? (
          <div className="settings-panel">
            {model.steps ? (
              <NumberField label="Steps" hint={`${model.steps.label}. ${model.steps.info}`} control={model.steps} value={steps} onChange={setSteps} />
            ) : null}
            {model.guidance ? (
              <Slider wide label="Guidance" hint={`${model.guidance.label}. ${model.guidance.info}`} control={model.guidance} value={guidance} onChange={setGuidance} />
            ) : null}
            <label title="Off uses a new seed each time. On repeats this one.">
              <span className="field-label seed-label">
                Seed
                <span className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={useSeed} onChange={(event) => setUseSeed(event.target.checked)} />
                  Lock
                </span>
              </span>
              <input type="number" aria-label="Seed" value={seed} onChange={(event) => setSeed(Number(event.target.value))} />
            </label>
          </div>
        ) : null}

        <button id="generate-button" type="button" disabled={busy} onClick={() => void onGenerate()}>
          {busy ? "Generating..." : "Generate"}
        </button>

        <details className="advanced-disclosure">
          <summary>Advanced</summary>
          <div className="mt-1 grid gap-1.5">
            <select aria-label="Instruments" multiple size={3} value={instruments} onChange={(event) => setInstruments(selectedValues(event))}>
              {instrumentChoices.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
            <select aria-label="Character" multiple size={3} value={character} onChange={(event) => setCharacter(selectedValues(event))}>
              {bootstrap.characters.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
            <input aria-label="Extra keywords" value={keywords} placeholder="Extra keywords" onChange={(event) => setKeywords(event.target.value)} />
          </div>
        </details>
        </>
        ) : (
        <div className="remix-tool">
          {model.supports_editing ? null : (
            <p className="text-xs">Stable Audio only.</p>
          )}
          <select aria-label="Track from history" value={remixTrack} onChange={(event) => setRemixTrack(event.target.value)}>
            <option value="">Track from history</option>
            {tracks.map((track) => (
              <option key={track.name} value={track.name}>{track.title}</option>
            ))}
          </select>
          <input
            aria-label="Upload a track"
            type="file"
            accept="audio/*,.wav,.mp3,.flac,.aiff,.aif,.ogg"
            onChange={(event) => setRemixFile(event.target.files?.[0] ?? null)}
          />
          <label title="Low keeps the melody and rhythm. High keeps only the timbre.">
            <span className="field-label">Change {remixNoise.toFixed(2)}</span>
            <input className="full-range" type="range" min={0.1} max={1.2} step={0.05} value={remixNoise} onChange={(event) => setRemixNoise(Number(event.target.value))} />
          </label>
          <textarea aria-label="Become" value={remixPrompt} placeholder="Become" onChange={(event) => setRemixPrompt(event.target.value)} />
          <button
            type="button"
            disabled={busy || !model.supports_editing}
            className="tool-submit"
            onClick={() => void onRemix()}
          >
            Remix track
          </button>
        </div>
        )}
        {notice ? (
          <p className={`notice-line ${notice.tone === "error" ? "text-[var(--discard)]" : "text-[var(--muted)]"}`}>
            {notice.text}
          </p>
        ) : null}
      </section>

      <HistoryDrawer
        mode={drawer}
        trackCount={tracks.length}
        activeCount={activeCount}
        focusJob={focusJob}
        draggingRef={draggingDrawer}
        onSettle={settleDrawer}
      >
        <QueueList
          jobs={queue}
          onMove={(id, direction) => void moveJob(id, direction).then((result) => setQueue(result.queue))}
          onRemove={(id) => void removeJob(id).then((result) => setQueue(result.queue))}
        />
        <div className="mb-2 grid shrink-0 grid-cols-3 gap-2">
          <select aria-label="Filter by genre" value={filterGenre} onChange={(event) => setFilterGenre(event.target.value)}>
            {genreFilters.map((name) => <option key={name} value={name}>{name === "any" ? "Any genre" : name}</option>)}
          </select>
          <select aria-label="Filter by rating" value={filterRating} onChange={(event) => setFilterRating(event.target.value)}>
            <option value="any">Any rating</option>
            <option value="keep">Keep</option>
            <option value="discard">Discard</option>
            <option value="unrated">Unrated</option>
          </select>
          <input aria-label="Search" value={filterQuery} onChange={(event) => setFilterQuery(event.target.value)} placeholder="Search" />
        </div>
        <div className="library-scroll">
          {pending.map((item) => (
            <div key={item.stem} className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)] px-3 py-2 text-sm">
              <span className="min-w-0">{item.title} deleted. {Math.ceil(item.seconds_left / 60)} min to undo.</span>
              <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1" onClick={() => void undoDelete(item.stem).then(applyLibrary)}>
                Undo delete
              </button>
            </div>
          ))}
          {visibleTracks.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">{tracks.length === 0 ? "No tracks yet." : "No tracks match."}</p>
          ) : (
            <div className="flex flex-col gap-3 pr-1">
              {visibleTracks.map((track) => (
                <TrackCard
                  key={track.name}
                  track={track}
                  onRate={(rating) => void rateTrack(track.name, rating).then(applyLibrary)}
                  onDelete={() => void deleteTrack(track.name).then(applyLibrary)}
                />
              ))}
            </div>
          )}
        </div>
      </HistoryDrawer>
    </div>
  );

  function applyLibrary(state: { tracks?: Track[]; pending: Pending[]; queue: Job[]; signature: string }) {
    setPending(state.pending);
    setQueue(state.queue);
    setSignature(state.signature);
    if (state.tracks) setTracks(state.tracks);
  }
}

function remixForm(shared: Record<string, unknown>, file: File) {
  const form = new FormData();
  for (const [key, value] of Object.entries(shared)) {
    if (value != null) form.set(key, String(value));
  }
  form.set("file", file);
  return form;
}

function Slider({
  label, hint, control, value, onChange, wide = false, format,
}: {
  label: string;
  hint: string;
  control: ModelInfo["duration"];
  value: number;
  onChange: (value: number) => void;
  wide?: boolean;
  format?: (value: number) => string;
}) {
  const shown = format
    ? format(value)
    : control.integer ? Math.round(value) : value;
  return (
    <label title={hint}>
      <span className="field-label">{label} {shown}</span>
      <input
        className={wide ? "full-range" : undefined}
        type="range"
        aria-label={label}
        min={control.minimum}
        max={control.maximum ?? control.minimum}
        step={control.step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function NumberField({
  label, hint, control, value, onChange,
}: {
  label: string;
  hint: string;
  control: ModelInfo["duration"];
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label title={hint}>
      <span className="field-label">{label}</span>
      <input
        type="number"
        aria-label={label}
        min={control.minimum}
        max={control.maximum ?? undefined}
        step={control.step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function HistoryDrawer({
  mode, trackCount, activeCount, focusJob, draggingRef, onSettle, children,
}: {
  mode: DrawerMode;
  trackCount: number;
  activeCount: number;
  focusJob: Job | null;
  draggingRef: RefObject<boolean>;
  onSettle: (next: DrawerMode) => void;
  children: ReactNode;
}) {
  const [dragHeight, setDragHeight] = useState<number | null>(null);
  const dragged = useRef(false);
  const panelRef = useRef<HTMLElement>(null);
  const resting = mode === "open"
    ? "100dvh"
    : mode === "peek"
      ? "calc(5.6rem + env(safe-area-inset-bottom))"
      : "calc(3.8rem + env(safe-area-inset-bottom))";
  const shown: DrawerMode = dragHeight == null ? mode : snapDrawer(
    dragHeight,
    window.innerHeight,
    focusJob != null,
  );

  function onPointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    const handle = event.currentTarget;
    const startY = event.clientY;
    const origin = panelRef.current?.getBoundingClientRect().height || 54;
    let latest = origin;
    dragged.current = false;
    draggingRef.current = true;
    handle.setPointerCapture(event.pointerId);
    const move = (ev: PointerEvent) => {
      const dy = startY - ev.clientY;
      if (Math.abs(dy) > 8) dragged.current = true;
      latest = Math.min(window.innerHeight, Math.max(52, origin + dy));
      setDragHeight(latest);
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      draggingRef.current = false;
      setDragHeight(null);
      if (!dragged.current) return;
      onSettle(snapDrawer(latest, window.innerHeight, focusJob != null));
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  }

  return (
    <section
      id="history-panel"
      ref={panelRef}
      className={`drawer drawer-${shown}${dragHeight != null ? " is-dragging" : ""}`}
      style={{ height: dragHeight != null ? `${dragHeight}px` : resting }}
    >
      <button
        type="button"
        className="drawer-handle"
        aria-expanded={shown === "open"}
        onPointerDown={onPointerDown}
        onClick={() => {
          if (dragged.current) {
            dragged.current = false;
            return;
          }
          if (mode === "open") onSettle(focusJob ? "peek" : "closed");
          else onSettle("open");
        }}
      >
        <span className="drawer-grabber" aria-hidden="true" />
        <span className="drawer-title-row">
          <span className="drawer-title">Track history</span>
          <span className="track-count" aria-label={`${trackCount} tracks`}>{trackCount}</span>
          {activeCount > 0 ? <QueueBadge count={activeCount} /> : null}
        </span>
      </button>
      {shown === "peek" && focusJob ? <PeekProgress job={focusJob} /> : null}
      {shown === "open" ? <div className="drawer-body">{children}</div> : null}
    </section>
  );
}

function PeekProgress({ job }: { job: Job }) {
  const queued = job.status === "queued";
  const width = queued ? "40%" : `${Math.max(0, Math.min(100, job.progress))}%`;
  return (
    <div className="drawer-progress" aria-label={job.status_text}>
      <span
        className={`drawer-progress-fill${queued ? " is-queued" : ""}`}
        style={{ width }}
      />
    </div>
  );
}

function QueueBadge({ count }: { count: number }) {
  return (
    <span className="queue-badge" aria-label={`${count} generating or queued`}>
      <svg className="queue-badge-ring" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M16 5a11 11 0 1 1-7.2 2.7" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M7.4 4.2 8.2 9l4.6-1.8" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="queue-badge-count">{count}</span>
    </span>
  );
}

function QueueList({
  jobs, onMove, onRemove,
}: {
  jobs: Job[];
  onMove: (id: string, direction: number) => void;
  onRemove: (id: string) => void;
}) {
  if (jobs.length === 0) return null;
  return (
    <div className="mb-2 flex shrink-0 flex-col gap-2">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} onMove={onMove} onRemove={onRemove} />
      ))}
    </div>
  );
}

function JobCard({
  job, onMove, onRemove,
}: {
  job: Job;
  onMove: (id: string, direction: number) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <article className={`queue-job ${job.status} rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-3`}>
      <div className="queue-job-header flex items-start justify-between gap-3">
        <p className="queue-job-title text-sm">{job.model} · {job.duration}s · seed {job.seed}</p>
        <p className="text-sm text-[var(--muted)]">{job.status_text}</p>
      </div>
      <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">{job.prompt}</p>
      {job.error ? <p className="mt-1 text-sm text-[var(--discard)]">{job.error}</p> : null}
      <div className="queue-job-track mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--panel-2)]">
        <span
          className="queue-job-fill block h-full bg-[var(--accent)]"
          style={{ width: job.status === "queued" ? "40%" : `${job.progress}%` }}
        />
      </div>
      <div className="card-actions mt-2 flex gap-2">
        {job.status === "queued" ? (
          <>
            <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => onMove(job.id, -1)}>Move up</button>
            <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => onMove(job.id, 1)}>Move down</button>
            <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => onRemove(job.id)}>Remove</button>
          </>
        ) : null}
        {job.status === "failed" ? (
          <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => onRemove(job.id)}>Dismiss</button>
        ) : null}
      </div>
    </article>
  );
}

function TrackCard({
  track, onRate, onDelete,
}: {
  track: Track;
  onRate: (rating: string | null) => void;
  onDelete: () => void;
}) {
  const peakMax = Math.max(...track.peaks, 0) || 1;
  const meta = [
    track.genre,
    formatSeconds(track.duration),
    track.rating,
    track.audit_status === "short" || track.audit_status === "long" || track.audit_status === "invalid"
      ? track.audit_status.toUpperCase()
      : null,
  ].filter(Boolean).join(" · ");
  return (
    <article className="history-card rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-4">
      <h2 className="history-title text-lg font-semibold">{track.title}</h2>
      <p className="text-sm text-[var(--muted)]">{meta || "No genre recorded"}</p>
      <div
        data-waveform
        role="slider"
        aria-label={`Seek ${track.title}`}
        aria-valuemin={0}
        aria-valuemax={100}
        className="mt-3 flex h-12 cursor-pointer items-center gap-px"
      >
        {track.peaks.length === 0 ? (
          <span className="text-xs text-[var(--muted)]">Waveform unavailable</span>
        ) : track.peaks.map((peak, index) => (
          <span
            key={index}
            className="block flex-1 rounded-sm bg-[var(--accent)]"
            style={{ height: `${Math.max(8, (peak / peakMax) * 100)}%` }}
          />
        ))}
      </div>
      <audio
        className="history-audio mt-2"
        controls
        preload="none"
        src={track.audio}
        ref={(node) => {
          if (node && node.dataset.bound !== "yes") {
            node.dataset.bound = "yes";
            bindExclusivePlayback(node);
          }
        }}
      />
      <details className="mt-3 text-sm text-[var(--muted)]">
        <summary>Details</summary>
        <p className="mt-2">
          {track.backend}
          {formatSeconds(track.duration) ? ` · ${formatSeconds(track.duration)} delivered` : ""}
          {track.requested_duration != null ? ` · ${track.requested_duration}s target` : ""}
          {track.seed != null ? ` · seed ${track.seed}` : ""}
          {track.sample_rate != null ? ` · ${track.sample_rate} Hz` : ""}
        </p>
        <p className="mt-1">{track.prompt}</p>
        {track.audit_error ? <p className="mt-1">{track.audit_error}</p> : null}
      </details>
      <div className="card-actions mt-3 flex gap-2">
        <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => onRate("keep")}>Keep</button>
        <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => onRate("discard")}>Discard</button>
        <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => onRate(null)}>Clear rating</button>
        <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={onDelete}>Delete</button>
      </div>
    </article>
  );
}
