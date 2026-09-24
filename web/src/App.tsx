import { useEffect, useMemo, useState, type ChangeEvent } from "react";
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
import { bindExclusivePlayback } from "./playback";

type Notice = { tone: "ok" | "error"; text: string } | null;

function selectedValues(event: ChangeEvent<HTMLSelectElement>) {
  return Array.from(event.target.selectedOptions).map((option) => option.value);
}

function formatSeconds(value: number | null) {
  if (value == null || !Number.isFinite(value)) return null;
  return Number.isInteger(value) ? `${value}s` : `${value.toFixed(1)}s`;
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

  if (!bootstrap || !model) {
    return <p className="p-8 text-[var(--muted)]">Loading the workbench.</p>;
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <header className="page-header flex shrink-0 items-center justify-between gap-3 px-4 py-3 sm:px-5">
        <h1 className="text-xl font-semibold tracking-tight">Music</h1>
        <label className="min-w-0 w-full max-w-xs">
          <select aria-label="Model" value={modelName} onChange={(event) => applyModel(event.target.value)} title={`${model.model_id}. ${model.licence}`}>
            {bootstrap.models.map((item) => (
              <option key={item.name} value={item.name}>{item.name}</option>
            ))}
          </select>
        </label>
      </header>

      <main className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-3 px-4 pb-3 sm:px-5 lg:grid-cols-[minmax(18rem,26rem)_minmax(0,1fr)] lg:grid-rows-1">
        <section id="controls-panel" className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto">
          <div className="grid gap-3">
            <label>
              <span className="mb-1 block text-xs text-[var(--muted)]">Genre</span>
              <select value={genre} onChange={(event) => void onGenre(event.target.value)}>
                <option value="">Choose a genre</option>
                {bootstrap.genres.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label title="Written into the prompt. The model has no tempo control.">
                <span className="mb-1 block text-xs text-[var(--muted)]">{bpm} BPM</span>
                <input type="range" min={50} max={200} step={1} value={bpm} onChange={(event) => setBpm(Number(event.target.value))} />
              </label>
              <label>
                <span className="mb-1 block text-xs text-[var(--muted)]">Mood</span>
                <select value={mood} onChange={(event) => setMood(event.target.value)}>
                  {moods.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-2" title={model.voice_info}>
              {model.voice_choices.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => setVocals(choice)}
                  className={`rounded-full border px-3 py-1 text-sm ${vocals === choice ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-ink)]" : "border-[var(--line)]"}`}
                >
                  {choice}
                </button>
              ))}
            </div>

            <div>
              <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-[var(--muted)]">Prompt</span>
                <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1 text-sm" onClick={() => void writePrompt(genre).catch((error: Error) => setNotice({ tone: "error", text: error.message }))}>Regenerate</button>
              </div>
              <textarea
                value={prompt}
                title={model.prompt_hint}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Edit the prompt"
              />
            </div>

            {model.supports_lyrics && vocals !== "Instrumental" ? (
              <textarea aria-label="Lyrics" value={lyrics} onChange={(event) => setLyrics(event.target.value)} placeholder="Lyrics" />
            ) : null}

            <div className="grid grid-cols-2 gap-3">
              <Slider label="Duration" hint={`${model.duration.label}. ${model.duration.info}`} control={model.duration} value={duration} onChange={setDuration} />
              {model.steps ? (
                <NumberField label="Steps" hint={`${model.steps.label}. ${model.steps.info}`} control={model.steps} value={steps} onChange={setSteps} />
              ) : null}
              {model.guidance ? (
                <Slider label="Guidance" hint={`${model.guidance.label}. ${model.guidance.info}`} control={model.guidance} value={guidance} onChange={setGuidance} />
              ) : null}
              <label title="Off uses a new seed each time. On repeats this one.">
                <span className="mb-1 flex items-center justify-between text-xs text-[var(--muted)]">
                  Seed
                  <span className="inline-flex items-center gap-1">
                    <input type="checkbox" checked={useSeed} onChange={(event) => setUseSeed(event.target.checked)} />
                    Lock
                  </span>
                </span>
                <input type="number" aria-label="Seed" value={seed} onChange={(event) => setSeed(Number(event.target.value))} />
              </label>
            </div>

            <button id="generate-button" type="button" disabled={busy} onClick={() => void onGenerate()}>
              {busy ? "Generating..." : "Generate"}
            </button>
            {notice ? (
              <p className={notice.tone === "error" ? "text-sm text-[var(--discard)]" : "text-sm text-[var(--muted)]"}>
                {notice.text}
              </p>
            ) : null}

            <details>
              <summary className="cursor-pointer text-sm">Advanced</summary>
              <div className="mt-2 grid gap-2">
                <select aria-label="Instruments" multiple size={4} value={instruments} onChange={(event) => setInstruments(selectedValues(event))}>
                  {instrumentChoices.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
                <select aria-label="Character" multiple size={4} value={character} onChange={(event) => setCharacter(selectedValues(event))}>
                  {bootstrap.characters.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
                <input aria-label="Extra keywords" value={keywords} placeholder="Extra keywords" onChange={(event) => setKeywords(event.target.value)} />
              </div>
            </details>

            <details>
              <summary className="cursor-pointer text-sm">Remix a track</summary>
              <div className="mt-2 grid gap-2">
                {model.supports_editing ? null : (
                  <p className="text-sm">Stable Audio only.</p>
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
                  <span className="mb-1 block text-xs text-[var(--muted)]">Change {remixNoise.toFixed(2)}</span>
                  <input type="range" min={0.1} max={1.2} step={0.05} value={remixNoise} onChange={(event) => setRemixNoise(Number(event.target.value))} />
                </label>
                <textarea aria-label="Become" value={remixPrompt} placeholder="Become" onChange={(event) => setRemixPrompt(event.target.value)} />
                <button
                  type="button"
                  disabled={busy || !model.supports_editing}
                  className="rounded-xl border border-[var(--line)] px-3 py-2"
                  onClick={() => void onRemix()}
                >
                  Remix track
                </button>
              </div>
            </details>

            <details>
              <summary className="cursor-pointer text-sm text-[var(--muted)]">About this model</summary>
              <p className="mt-2 text-sm text-[var(--muted)]">
                {model.model_id}. {model.available ? "Ready" : "Setup missing"}. {model.licence}. Max {Math.round(model.max_duration)}s. {model.notes}
              </p>
            </details>
          </div>

          <QueueList
            jobs={queue}
            onMove={(id, direction) => void moveJob(id, direction).then((result) => setQueue(result.queue))}
            onRemove={(id) => void removeJob(id).then((result) => setQueue(result.queue))}
          />
        </section>

        <section id="history-panel" className="min-h-0 min-w-0">
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
        </section>
      </main>
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
  label, hint, control, value, onChange,
}: {
  label: string;
  hint: string;
  control: ModelInfo["duration"];
  value: number;
  onChange: (value: number) => void;
}) {
  const shown = control.integer ? Math.round(value) : value;
  return (
    <label title={hint}>
      <span className="mb-1 block text-xs text-[var(--muted)]">{label} {shown}</span>
      <input
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
      <span className="mb-1 block text-xs text-[var(--muted)]">{label}</span>
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

function QueueList({
  jobs, onMove, onRemove,
}: {
  jobs: Job[];
  onMove: (id: string, direction: number) => void;
  onRemove: (id: string) => void;
}) {
  if (jobs.length === 0) return null;
  return (
    <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
      {jobs.map((job) => (
        <article key={job.id} className={`queue-job ${job.status} rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-3`}>
          <div className="queue-job-header flex items-start justify-between gap-3">
            <p className="queue-job-title text-sm">{job.model} · {job.duration}s · seed {job.seed}</p>
            <p className="text-sm text-[var(--muted)]">{job.status_text}</p>
          </div>
          <p className="mt-1 text-sm text-[var(--muted)]">{job.prompt}</p>
          {job.error ? <p className="mt-1 text-sm text-[var(--discard)]">{job.error}</p> : null}
          <div className="queue-job-track mt-3 h-1.5 overflow-hidden rounded-full bg-[var(--panel-2)]">
            <span
              className="queue-job-fill block h-full bg-[var(--accent)]"
              style={{ width: job.status === "queued" ? "40%" : `${job.progress}%` }}
            />
          </div>
          <div className="card-actions mt-3 flex gap-2">
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
      ))}
    </div>
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
