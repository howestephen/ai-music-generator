"""Local web UI. A thin wrapper over synth.core and the generated output folder.

Everything model-specific (licence, prompt style, duration cap and available knobs) is
read from the backend registry. Track history is rebuilt from the WAV files and JSON
sidecars already written by ``core.generate``; the UI owns no second copy of that data.
"""
from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path

import gradio as gr
import soundfile as sf

from synth import backends, core

# Starting points for work-video backing tracks in each backend's prompt language.
PRESETS = {
    "Corporate / uplifting": {
        "tags": "uplifting corporate, bright piano, subtle strings, steady four-on-the-floor, optimistic, 110bpm, instrumental",
        "caption": "Global Metadata: Genre: corporate. BPM: 110. Mood: uplifting and optimistic. Arrangement: bright piano, subtle strings and a steady four-on-the-floor rhythm. Instrumental only, no vocals.",
    },
    "Lo-fi / relaxed": {
        "tags": "lo-fi hip hop, warm rhodes piano, soft vinyl crackle, mellow drums, relaxed, 85bpm, instrumental",
        "caption": "Global Metadata: Genre: lo-fi hip hop. BPM: 85. Mood: relaxed. Arrangement: warm Rhodes piano, soft vinyl crackle and mellow drums. Instrumental only, no vocals.",
    },
    "Ambient / underscore": {
        "tags": "ambient underscore, soft evolving pads, sparse piano notes, gentle, unobtrusive, no drums, instrumental",
        "caption": "Global Metadata: Genre: ambient underscore. Mood: gentle and unobtrusive. Arrangement: soft evolving pads and sparse piano notes, with no drums. Instrumental only, no vocals.",
    },
    "Tech / explainer": {
        "tags": "minimal electronic, clean plucky synth arpeggio, light percussion, curious and modern, 100bpm, instrumental",
        "caption": "Global Metadata: Genre: minimal electronic. BPM: 100. Mood: curious and modern. Arrangement: a clean, plucky synth arpeggio with light percussion. Instrumental only, no vocals.",
    },
    "Tension / build": {
        "tags": "cinematic tension, low pulsing strings, rising drone, building anticipation, sparse percussion, instrumental",
        "caption": "Global Metadata: Genre: cinematic tension. Mood: building anticipation. Arrangement: low pulsing strings, a rising drone and sparse percussion. Instrumental only, no vocals.",
    },
}

UI_CSS = """
#generate-button:disabled {
    background: var(--button-secondary-background-fill);
    color: transparent;
    isolation: isolate;
    background-color: var(--button-secondary-background-fill);
    opacity: 1;
    overflow: hidden;
    position: relative;
}

#generate-button:disabled::before {
    animation: generation-progress 1.4s ease-in-out infinite;
    background: var(--button-primary-background-fill);
    content: "";
    inset: 0;
    position: absolute;
    transform: translateX(-105%);
    width: 55%;
    z-index: 0;
}

#generate-button:disabled::after {
    background: var(--button-secondary-background-fill);
    border-radius: var(--button-large-radius);
    color: var(--button-secondary-text-color);
    content: "Generating...";
    left: 50%;
    padding: 0.2rem 0.75rem;
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    z-index: 1;
}

#history-panel,
.history-audio {
    min-width: 0;
}

.history-waveform {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: var(--block-radius);
    color: var(--neutral-400);
    cursor: pointer;
    height: 4.25rem;
    overflow: hidden;
    position: relative;
    width: 100%;
}

.history-waveform:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
}

.history-waveform svg {
    display: block;
    height: 100%;
    width: 100%;
}

.history-waveform-cursor {
    background: var(--button-primary-background-fill);
    bottom: 0;
    left: var(--waveform-position, 0%);
    pointer-events: none;
    position: absolute;
    top: 0;
    width: 2px;
}

.history-audio .waveform-container,
.history-audio .timestamps,
.history-audio .subtitle-display {
    display: none;
}

@keyframes generation-progress {
    from { transform: translateX(-105%); }
    to { transform: translateX(190%); }
}

@media (prefers-reduced-motion: reduce) {
    #generate-button:disabled::before {
        animation: none;
        transform: translateX(40%);
    }
}
"""

UI_JS = """
(() => {
    const wiredPlayers = new WeakSet();

    const playerFor = (waveform) => {
        const host = waveform.closest(".history-card")
            ?.querySelector(".history-audio #waveform > div");
        return host?.shadowRoot?.querySelector("audio");
    };

    const showPosition = (waveform, audio) => {
        if (!Number.isFinite(audio.duration) || audio.duration === 0) return;
        const percent = Math.max(0, Math.min(100, audio.currentTime / audio.duration * 100));
        waveform.style.setProperty("--waveform-position", `${percent}%`);
        waveform.setAttribute("aria-valuenow", `${Math.round(percent)}`);
    };

    const wirePlayers = () => {
        document.querySelectorAll(".history-waveform").forEach((waveform) => {
            const audio = playerFor(waveform);
            if (!audio || wiredPlayers.has(audio)) return;
            wiredPlayers.add(audio);
            ["loadedmetadata", "seeking", "timeupdate"]
                .forEach((eventName) => audio.addEventListener(
                    eventName,
                    () => showPosition(waveform, audio),
                ));
            showPosition(waveform, audio);
        });
    };

    const seek = (waveform, position) => {
        const audio = playerFor(waveform);
        if (!audio || !Number.isFinite(audio.duration)) return;
        audio.currentTime = Math.max(0, Math.min(1, position)) * audio.duration;
        showPosition(waveform, audio);
    };

    document.addEventListener("click", (event) => {
        const waveform = event.target.closest(".history-waveform");
        if (!waveform) return;
        const bounds = waveform.getBoundingClientRect();
        seek(waveform, (event.clientX - bounds.left) / bounds.width);
    });

    document.addEventListener("keydown", (event) => {
        const waveform = event.target.closest(".history-waveform");
        if (!waveform || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        const audio = playerFor(waveform);
        if (!audio || !Number.isFinite(audio.duration)) return;
        event.preventDefault();
        const seconds = event.key === "ArrowLeft" ? -5 : 5;
        seek(waveform, (audio.currentTime + seconds) / audio.duration);
    });

    new MutationObserver(() => requestAnimationFrame(wirePlayers))
        .observe(document.body, {childList: true, subtree: true});
    requestAnimationFrame(wirePlayers);
})();
"""


def _prompt_hint(backend: backends.Backend) -> str:
    if backend.prompt_style == "tags":
        return "Style tags beat sentences: `warm rhodes, 85bpm, mellow`."
    return "Use a structured caption in prose: genre, BPM, key, scale and arrangement."


def _preset_prompt(name: str | None, model: str) -> str:
    if not name:
        return ""
    prompts = PRESETS.get(name)
    if not prompts:
        return ""
    return prompts[backends.get(model).prompt_style]


def _backend_summary(model: str) -> str:
    backend = backends.get(model)
    availability = "Configured" if backend.available else "Setup missing"
    return (
        f"**{backend.model_id}**  \n"
        f"{availability} · {backend.licence} · maximum {backend.max_duration:.0f}s  \n"
        f"{backend.notes}"
    )


def _model_updates(model, duration, preset):
    backend = backends.get(model)
    duration = min(float(duration), backend.max_duration)
    prompt = _preset_prompt(preset, model) if preset else gr.update()
    return (
        _backend_summary(model),
        gr.update(maximum=int(backend.max_duration), value=duration),
        gr.update(value=backend.default_steps or 60, visible=backend.default_steps is not None),
        gr.update(
            value=backend.default_guidance or 15,
            visible=backend.default_guidance is not None,
        ),
        _prompt_hint(backend),
        prompt,
    )


def _load_history(output_dir: Path | None = None) -> list[dict]:
    output_dir = Path(output_dir) if output_dir else core.OUTPUT_DIR
    if not output_dir.exists():
        return []

    tracks = []
    for path in output_dir.glob("*.wav"):
        metadata = {}
        try:
            metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
            pass
        if not isinstance(metadata, dict):
            metadata = {}
        try:
            modified_ns = path.stat().st_mtime_ns
        except OSError:
            continue
        tracks.append({
            "path": str(path),
            "name": path.name,
            "modified_ns": modified_ns,
            "backend": metadata.get("backend", "unknown model"),
            "duration": metadata.get("duration"),
            "seed": metadata.get("seed"),
            "prompt": metadata.get("prompt", "Prompt unavailable"),
            "generated_at": metadata.get("generated_at", "Time unavailable"),
        })
    return sorted(tracks, key=lambda item: (item["modified_ns"], item["name"]), reverse=True)


def _history_copy(track: dict) -> str:
    details = [html.escape(str(track["backend"]))]
    if track["duration"] is not None:
        try:
            details.append(f"{float(track['duration']):g}s")
        except (TypeError, ValueError, OverflowError):
            pass
    if track["seed"] is not None:
        details.append(f"seed {html.escape(str(track['seed']))}")
    return (
        f"**{html.escape(track['name'])}**  \n"
        f"{' · '.join(details)} · {html.escape(str(track['generated_at']))}  \n"
        f"{html.escape(str(track['prompt']))}"
    )


@lru_cache(maxsize=256)
def _waveform_peaks(path_string: str, modified_ns: int, bars: int = 120) -> tuple[float, ...]:
    del modified_ns  # Part of the cache key, so a replaced WAV is read again.
    try:
        with sf.SoundFile(path_string) as audio:
            if len(audio) == 0:
                return ()
            peaks = []
            for index in range(bars):
                start = round(index * len(audio) / bars)
                end = round((index + 1) * len(audio) / bars)
                audio.seek(start)
                samples = audio.read(end - start, dtype="float32", always_2d=True)
                peaks.append(float(abs(samples).max()) if samples.size else 0.0)
    except (OSError, RuntimeError, ValueError):
        return ()
    return tuple(peaks)


def _history_waveform(track: dict) -> str:
    peaks = _waveform_peaks(track["path"], track["modified_ns"])
    if not peaks:
        bars = '<text x="50" y="22" text-anchor="middle">Waveform unavailable</text>'
    else:
        peak_max = max(peaks) or 1.0
        rects = []
        for index, peak in enumerate(peaks):
            height = max(1.0, peak / peak_max * 34)
            rects.append(
                f'<rect x="{index + 0.15:g}" y="{20 - height / 2:g}" '
                f'width="0.7" height="{height:g}" rx="0.25" />'
            )
        bars = "".join(rects)
    label = html.escape(f"Seek through {track['name']}", quote=True)
    return (
        f'<div class="history-waveform" role="slider" tabindex="0" '
        f'aria-label="{label}" aria-valuemin="0" aria-valuemax="100" '
        'aria-valuenow="0">'
        '<svg viewBox="0 0 120 40" preserveAspectRatio="none" aria-hidden="true">'
        f'{bars}</svg><span class="history-waveform-cursor"></span></div>'
    )


def _generation_started():
    return gr.update(value="Generating...", interactive=False, variant="secondary")


def _generation_finished():
    return gr.update(value="Generate", interactive=True, variant="primary")


def _generate(model, prompt, duration, steps, guidance, seed, use_seed):
    if not prompt or not prompt.strip():
        raise gr.Error("Enter a prompt first.")
    backend = backends.get(model)
    try:
        track = core.generate(
            prompt=prompt.strip(),
            duration=duration,
            seed=int(seed) if use_seed else None,
            # Only hand over the knobs this backend actually has; None means its default.
            infer_step=int(steps) if backend.default_steps is not None else None,
            guidance_scale=guidance if backend.default_guidance is not None else None,
            model=backend.name,
        )
    except Exception as exc:
        raise gr.Error(str(exc)) from exc
    status = (
        f"**Generated {track.path.name}**  \n"
        f"Seed `{track.seed}` · {track.elapsed_seconds}s to generate · {track.duration:.0f}s long. "
        "It is now first in the track history."
    )
    return status, track.seed, _load_history()


def build_ui() -> gr.Blocks:
    initial_backend = backends.get(core.DEFAULT_MODEL)
    model_choices = [
        (f"{name} · {backend.model_id}", name)
        for name, backend in backends.BACKENDS.items()
    ]
    with gr.Blocks(title="Background Music Generator") as demo:
        gr.Markdown("# Background Music Generator\nLocal instrumental music, generated on this machine.")

        with gr.Row(equal_height=False):
            with gr.Column(scale=1, elem_id="controls-panel"):
                model = gr.Dropdown(
                    choices=model_choices,
                    value=core.DEFAULT_MODEL,
                    label="Model",
                )
                model_summary = gr.Markdown(_backend_summary(core.DEFAULT_MODEL))
                preset = gr.Radio(
                    choices=list(PRESETS), label="Presets", value=None,
                    info="Loads a starting prompt below. Then edit it.",
                )
                prompt = gr.Textbox(
                    label="Prompt", lines=3,
                    placeholder="lo-fi hip hop, warm rhodes piano, soft vinyl crackle, 85bpm, instrumental",
                )
                prompt_help = gr.Markdown(_prompt_hint(initial_backend))
                with gr.Row():
                    duration = gr.Slider(10, int(initial_backend.max_duration),
                                         value=min(60, int(initial_backend.max_duration)),
                                         step=5, label="Duration (s)")
                    steps = gr.Slider(20, 120, value=initial_backend.default_steps or 60,
                                      step=1, label="Steps",
                                      info="Lower = faster, rougher",
                                      visible=initial_backend.default_steps is not None)
                with gr.Row():
                    guidance = gr.Slider(1, 30, value=initial_backend.default_guidance or 15,
                                         step=0.5,
                                         label="Prompt adherence",
                                         visible=initial_backend.default_guidance is not None)
                    seed = gr.Number(value=42, precision=0, label="Seed")
                use_seed = gr.Checkbox(
                    value=False, label="Lock seed",
                    info="Off = new random seed each time. On = reproduce an exact track.",
                )
                go = gr.Button("Generate", variant="primary", elem_id="generate-button")

            with gr.Column(scale=1, elem_id="history-panel"):
                gr.Markdown("## Latest result")
                status = gr.Markdown("Generate a track and it will appear first below.")

                with gr.Row():
                    gr.Markdown("## Track history")
                    refresh = gr.Button("Refresh history", size="sm")
                history = gr.State(_load_history())

                @gr.render(inputs=history)
                def render_history(tracks):
                    if not tracks:
                        gr.Markdown("No generated tracks yet.")
                        return
                    for track in tracks:
                        with gr.Group(elem_classes="history-card"):
                            gr.HTML(
                                _history_waveform(track),
                                key=f"waveform-{track['path']}",
                            )
                            gr.Audio(
                                value=track["path"],
                                show_label=False,
                                interactive=False,
                                editable=False,
                                elem_classes="history-audio",
                                key=f"audio-{track['path']}",
                            )
                            gr.Markdown(
                                _history_copy(track),
                                key=f"details-{track['path']}",
                            )

        model.change(
            _model_updates,
            [model, duration, preset],
            [model_summary, duration, steps, guidance, prompt_help, prompt],
        )
        preset.change(_preset_prompt, [preset, model], prompt)

        refresh.click(_load_history, outputs=history)
        request = go.click(
            _generation_started,
            outputs=go,
            queue=False,
            show_progress="hidden",
        )
        generation = request.then(
            _generate,
            [model, prompt, duration, steps, guidance, seed, use_seed],
            [status, seed, history],
            show_progress="full",
            show_progress_on=go,
        )
        generation.success(
            _generation_finished,
            outputs=go,
            queue=False,
            show_progress="hidden",
        )
        generation.failure(
            _generation_finished,
            outputs=go,
            queue=False,
            show_progress="hidden",
        )
    return demo


def main(share: bool = False, port: int = 7860) -> None:
    build_ui().launch(
        share=share,
        server_port=port,
        inbrowser=True,
        css=UI_CSS,
        js=UI_JS,
    )


if __name__ == "__main__":
    main()
