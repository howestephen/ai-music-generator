"""Adversarial checks for the backend seam.

Run:  ./.venv/bin/python -m unittest synth.tests -v

No model is loaded. The subprocess runner is stubbed so each test sees exactly what
`core.generate` hands to a backend and exactly what lands in the sidecar. The in-process
ACE-Step path is not covered here: it would load 7.7 GB of weights.
"""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from synth import backends, cli, core


class _StubRunner:
    """Records the job dict and pretends to have written the WAV."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, backend: backends.Backend, job: dict) -> dict:
        self.calls.append((backend.name, job))
        Path(job["output_path"]).write_bytes(b"RIFF")
        return {"elapsed_seconds": 0.1}

    @property
    def last_job(self) -> dict:
        return self.calls[-1][1]


class GenerateSeam(unittest.TestCase):
    def setUp(self) -> None:
        self.stub = _StubRunner()
        patcher = mock.patch.object(backends, "run_subprocess", self.stub)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def gen(self, **kw) -> core.Track:
        return core.generate(prompt="probe", duration=5.0, seed=1, output_dir=self.out, **kw)

    # --- steps -----------------------------------------------------------
    def test_explicit_steps_reach_minimax(self):
        self.gen(model="minimax-mlx", infer_step=12)
        self.assertEqual(self.stub.last_job["steps"], 12)

    def test_minimax_default_steps_are_its_own_not_the_cli_flat_60(self):
        track = self.gen(model="minimax-mlx")
        self.assertEqual(self.stub.last_job["steps"], 30)
        self.assertEqual(track.infer_step, 30)

    def test_zero_steps_is_refused_not_dropped(self):
        with self.assertRaises(ValueError):
            self.gen(model="minimax-mlx", infer_step=0)

    def test_musicgen_refuses_steps_it_has_no_control_for(self):
        with self.assertRaises(ValueError):
            self.gen(model="musicgen", infer_step=40)

    def test_musicgen_sidecar_records_no_step_count(self):
        self.assertIsNone(self.gen(model="musicgen").infer_step)

    # --- guidance --------------------------------------------------------
    def test_minimax_refuses_guidance_rather_than_dropping_it(self):
        with self.assertRaises(ValueError):
            self.gen(model="minimax-mlx", guidance_scale=9.0)

    def test_minimax_sidecar_records_no_guidance(self):
        self.assertIsNone(self.gen(model="minimax-mlx").guidance_scale)

    def test_musicgen_default_guidance_is_3_not_15(self):
        track = self.gen(model="musicgen")
        self.assertEqual(self.stub.last_job["guidance"], 3.0)
        self.assertEqual(track.guidance_scale, 3.0)

    def test_musicgen_explicit_guidance_still_wins(self):
        self.gen(model="musicgen", guidance_scale=4.5)
        self.assertEqual(self.stub.last_job["guidance"], 4.5)

    # --- lyrics ----------------------------------------------------------
    def test_musicgen_refuses_lyrics(self):
        with self.assertRaises(ValueError):
            self.gen(model="musicgen", lyrics="la la la")

    def test_minimax_gets_its_own_instrumental_sentinel(self):
        self.gen(model="minimax-mlx")
        self.assertEqual(self.stub.last_job["lyrics"], "[Instrumental]")

    # --- sidecar ---------------------------------------------------------
    def test_dtype_is_per_backend_not_acestep_float32_for_everyone(self):
        self.assertEqual(self.gen(model="minimax-mlx").dtype, "8-bit (MLX)")
        self.assertEqual(self.gen(model="musicgen").dtype, "float32")

    def test_sidecar_backend_key_is_what_the_cli_accepts(self):
        track = self.gen(model="minimax-mlx")
        side = json.loads(track.sidecar_path().read_text())
        self.assertEqual(side["backend"], "minimax-mlx")
        # The README says: feed the sidecar's backend and seed straight back in.
        args = cli.build_parser().parse_args(
            ["gen", side["prompt"], "-m", side["backend"], "--seed", str(side["seed"])]
        )
        self.assertEqual((args.model, args.seed), ("minimax-mlx", 1))

    def test_sidecar_still_records_the_weights_id(self):
        side = json.loads(self.gen(model="minimax-mlx").sidecar_path().read_text())
        self.assertEqual(side["model"], "vanch007/MiniMax-Music3-MLX-8bit")

    def test_sidecar_never_claims_a_knob_that_did_not_apply(self):
        side = json.loads(self.gen(model="minimax-mlx").sidecar_path().read_text())
        self.assertIsNone(side["guidance_scale"])
        side = json.loads(self.gen(model="musicgen").sidecar_path().read_text())
        self.assertIsNone(side["infer_step"])


class MinimaxRunnerArgv(unittest.TestCase):
    """The runner builds the real CLI command; nothing above it sees that argv."""

    def _run(self, job: dict) -> list[str]:
        spec = importlib.util.spec_from_file_location(
            "minimax_runner", core.PROJECT_ROOT / "runners" / "minimax_mlx_runner.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            return mock.Mock(returncode=0, stderr="")

        with mock.patch.object(runner.subprocess, "run", fake_run), \
                mock.patch.object(runner.sys, "stdin", io.StringIO(json.dumps(job))), \
                mock.patch.object(runner.sys, "stdout", io.StringIO()):
            self.assertEqual(runner.main(), 0)
        return seen["cmd"]

    def _job(self, **over) -> dict:
        base = {"prompt": "p", "lyrics": "[Instrumental]", "duration": 5.0, "seed": 1,
                "steps": 30, "guidance": None, "output_path": "/tmp/x.wav"}
        return {**base, **over}

    def test_steps_reach_the_cli(self):
        cmd = self._run(self._job(steps=12))
        self.assertIn("--steps", cmd)
        self.assertEqual(cmd[cmd.index("--steps") + 1], "12")

    def test_zero_steps_is_passed_not_dropped(self):
        cmd = self._run(self._job(steps=0))
        self.assertIn("--steps", cmd)

    def test_missing_steps_key_still_works(self):
        job = self._job(); del job["steps"]
        self.assertNotIn("--steps", self._run(job))

    def test_no_guidance_flag_is_ever_sent(self):
        cmd = self._run(self._job())
        self.assertFalse(any("guidance" in c or "cfg" in c for c in cmd))


class CliDefaults(unittest.TestCase):
    def test_steps_and_guidance_default_to_none_so_backend_defaults_win(self):
        args = cli.build_parser().parse_args(["gen", "x"])
        self.assertIsNone(args.steps)
        self.assertIsNone(args.guidance)

    def test_every_registry_key_is_a_valid_model_choice(self):
        for name in backends.BACKENDS:
            args = cli.build_parser().parse_args(["gen", "x", "-m", name])
            self.assertEqual(args.model, name)


class Registry(unittest.TestCase):
    def test_every_backend_declares_a_dtype(self):
        for b in backends.BACKENDS.values():
            self.assertTrue(b.dtype, b.name)

    def test_musicgen_is_flagged_non_commercial(self):
        self.assertIn("NON-COMMERCIAL", backends.get("musicgen").licence)


if __name__ == "__main__":
    unittest.main()
