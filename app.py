"""Local web UI. A thin wrapper over synth.core and the generated output folder.

Everything model-specific (licence, prompt style, duration cap and available knobs) is
read from the backend registry. Track history is rebuilt from the WAV files and JSON
sidecars already written by ``core.generate``; the UI owns no second copy of that data.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import gradio as gr

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
    animation: generation-progress 1.2s linear infinite;
    background-color: var(--button-secondary-background-fill);
    background-image: linear-gradient(
        90deg,
        transparent 0%,
        transparent 35%,
        var(--button-primary-background-fill) 50%,
        transparent 65%,
        transparent 100%
    );
    background-repeat: no-repeat;
    background-size: 250% 0.35rem;
    color: var(--button-secondary-text-color);
    opacity: 1;
}

@keyframes generation-progress {
    from { background-position: 100% 100%; }
    to { background-position: 0 100%; }
}

@media (prefers-reduced-motion: reduce) {
    #generate-button:disabled {
        animation: none;
        background: var(--button-secondary-background-fill);
        box-shadow: inset 0 -0.35rem 0 var(--button-primary-background-fill);
    }
}
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
        "It is now first in the history below."
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

        with gr.Row():
            with gr.Column(scale=3):
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

            with gr.Column(scale=2):
                gr.Markdown("## Latest result")
                status = gr.Markdown("Generate a track and it will appear first in the history.")

        model.change(
            _model_updates,
            [model, duration, preset],
            [model_summary, duration, steps, guidance, prompt_help, prompt],
        )
        preset.change(_preset_prompt, [preset, model], prompt)

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
                with gr.Row():
                    gr.Audio(
                        value=track["path"],
                        label=track["name"],
                        interactive=False,
                        key=f"audio-{track['path']}",
                    )
                    gr.Markdown(_history_copy(track), key=f"details-{track['path']}")

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
    build_ui().launch(share=share, server_port=port, inbrowser=True, css=UI_CSS)


if __name__ == "__main__":
    main()
