"""Local web UI. A thin wrapper over synth.core - no logic lives here."""
from __future__ import annotations

import gradio as gr

from synth import core

# Starting points for work-video backing tracks. Edit freely - they're just prompt text.
PRESETS = {
    "Corporate / uplifting": "uplifting corporate, bright piano, subtle strings, steady four-on-the-floor, optimistic, 110bpm, instrumental",
    "Lo-fi / relaxed": "lo-fi hip hop, warm rhodes piano, soft vinyl crackle, mellow drums, relaxed, 85bpm, instrumental",
    "Ambient / underscore": "ambient underscore, soft evolving pads, sparse piano notes, gentle, unobtrusive, no drums, instrumental",
    "Tech / explainer": "minimal electronic, clean plucky synth arpeggio, light percussion, curious and modern, 100bpm, instrumental",
    "Tension / build": "cinematic tension, low pulsing strings, rising drone, building anticipation, sparse percussion, instrumental",
}


def _generate(prompt, duration, steps, guidance, seed, use_seed):
    if not prompt or not prompt.strip():
        raise gr.Error("Enter a prompt first - style tags work better than sentences.")
    track = core.generate(
        prompt=prompt.strip(),
        duration=duration,
        seed=int(seed) if use_seed else None,
        infer_step=int(steps),
        guidance_scale=guidance,
        )
    status = (
        f"**{track.path.name}**\n\n"
        f"Seed `{track.seed}` · {track.elapsed_seconds}s to generate · {track.duration:.0f}s long\n\n"
        f"Saved to `output/` with a matching `.json` so you can reproduce it."
    )
    return str(track.path), status, track.seed


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Background Music Generator") as demo:
        gr.Markdown(
            "# Background Music Generator\n"
            "Local instrumental music via ACE-Step (Apache 2.0). "
            "Style tags beat sentences: *`warm rhodes, 85bpm, mellow`* rather than *`something chill`*."
        )

        with gr.Row():
            with gr.Column(scale=3):
                preset = gr.Radio(
                    choices=list(PRESETS), label="Presets", value=None,
                    info="Loads a starting prompt below - then edit it.",
                )
                prompt = gr.Textbox(
                    label="Prompt", lines=3,
                    placeholder="lo-fi hip hop, warm rhodes piano, soft vinyl crackle, 85bpm, instrumental",
                )
                with gr.Row():
                    duration = gr.Slider(10, 240, value=60, step=5, label="Duration (s)")
                    steps = gr.Slider(20, 120, value=60, step=1, label="Steps",
                                      info="Lower = faster, rougher")
                with gr.Row():
                    guidance = gr.Slider(1, 30, value=15, step=0.5, label="Prompt adherence")
                    seed = gr.Number(value=42, precision=0, label="Seed")
                use_seed = gr.Checkbox(
                    value=False, label="Lock seed",
                    info="Off = new random seed each time. On = reproduce an exact track.",
                )
                go = gr.Button("Generate", variant="primary")

            with gr.Column(scale=2):
                audio = gr.Audio(label="Result", type="filepath")
                status = gr.Markdown()

        preset.change(lambda name: PRESETS.get(name, ""), preset, prompt)
        go.click(
            _generate,
            [prompt, duration, steps, guidance, seed, use_seed],
            [audio, status, seed],
        )
    return demo


def main(share: bool = False, port: int = 7860) -> None:
    build_ui().launch(share=share, server_port=port, inbrowser=True)


if __name__ == "__main__":
    main()
