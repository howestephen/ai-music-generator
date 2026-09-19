"""Adversarial checks for the backend seam and local UI.

Run:  ./.venv/bin/python -m unittest synth.tests -v

No model is loaded. The subprocess runner is stubbed so each test sees exactly what
`core.generate` hands to a backend and exactly what lands in the sidecar. The in-process
ACE-Step path is not covered here: it would load 7.7 GB of weights.
"""
from __future__ import annotations

import importlib.util
import io
import json
import math
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import app
import soundfile as sf
from synth import analyze, backends, cli, core, jobs


def _write_test_wav(path: Path, frames: int = 1) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x01\x00" * frames)


class _StubRunner:
    """Records the job dict and pretends to have written the WAV."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, backend: backends.Backend, job: dict) -> dict:
        self.calls.append((backend.name, job))
        path = Path(job["output_path"])
        _write_test_wav(path, frames=round(float(job["duration"]) * 8000))
        return {"path": str(path), "elapsed_seconds": 0.1}

    @property
    def last_job(self) -> dict:
        return self.calls[-1][1]


class GenerateSeam(unittest.TestCase):
    def setUp(self) -> None:
        self.stub = _StubRunner()
        patcher = mock.patch.object(backends, "run_subprocess", self.stub)
        patcher.start()
        self.addCleanup(patcher.stop)
        available = mock.patch.object(
            backends.Backend,
            "available",
            new_callable=mock.PropertyMock,
            return_value=True,
        )
        available.start()
        self.addCleanup(available.stop)
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def gen(self, **kw) -> core.Track:
        duration = kw.pop("duration", 5.0)
        return core.generate(prompt="probe", duration=duration, seed=1, output_dir=self.out, **kw)

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

    def test_minimax_accepts_duration_beyond_acestep_cap(self):
        track = self.gen(model="minimax-mlx", duration=270)
        self.assertEqual(track.duration, 270)
        self.assertEqual(track.requested_duration, 270)
        self.assertEqual(self.stub.last_job["duration"], 270)

    def test_fractional_duration_matches_runner_request_and_sidecar(self):
        track = self.gen(model="minimax-mlx", duration=1.5)
        sidecar = json.loads(track.sidecar_path().read_text(encoding="utf-8"))
        self.assertEqual(self.stub.last_job["duration"], 1.5)
        self.assertEqual(track.duration, 1.5)
        self.assertEqual(sidecar["duration"], 1.5)
        self.assertEqual(sidecar["requested_duration"], 1.5)
        self.assertEqual(sidecar["audit_status"], "passed")

    def _as_exact_backend(self, name="minimax-mlx", tolerance=0.05):
        """Give a real backend an exact duration contract for one test."""
        backend = backends.get(name)
        policy = backends.OutputAuditPolicy.from_manifest(
            {
                "minimum_duration_ratio": 1,
                "duration_tolerance_seconds": tolerance,
                "random_seed_retries": 0,
                "duration_contract": "exact",
            },
            "probe",
        )
        patched = dict(backends.BACKENDS)
        patched[name] = replace(backend, output_audit=policy)
        patcher = mock.patch.dict(backends.BACKENDS, patched, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fixed_length_runner(self, seconds):
        def runner(backend, job):
            path = Path(job["output_path"])
            _write_test_wav(path, frames=int(seconds * 8000))
            return {"path": str(path), "elapsed_seconds": 1.0}

        return runner

    def test_exact_contract_passes_a_render_inside_its_tolerance(self):
        self._as_exact_backend()
        with mock.patch.object(
            backends, "run_subprocess", self._fixed_length_runner(60.02)
        ):
            track = self.gen(model="minimax-mlx", duration=60)
        self.assertEqual(track.audit_status, "passed")

    def test_exact_contract_rejects_an_overlong_render_instead_of_accepting_it(self):
        """A best-effort backend would accept anything at or above its ratio, so a
        model that overshoots its target would pass silently. Under an exact contract
        that is an integration fault and must fail."""
        self._as_exact_backend()
        with mock.patch.object(
            backends, "run_subprocess", self._fixed_length_runner(75)
        ):
            with self.assertRaises(core.OutputAuditError) as raised:
                self.gen(model="minimax-mlx", duration=60)
        track = raised.exception.track
        sidecar = json.loads(track.sidecar_path().read_text(encoding="utf-8"))
        self.assertTrue(track.path.is_file())
        self.assertEqual(track.audit_status, "long")
        self.assertEqual(sidecar["audit_status"], "long")
        self.assertEqual(track.duration, 75)
        self.assertEqual(track.requested_duration, 60)
        self.assertIn("Overlong output retained", str(raised.exception))
        self.assertIn("maximum accepted", str(raised.exception))

    def test_exact_contract_rejects_a_render_a_hair_under_its_target(self):
        """The 0.9 ratio that MiniMax needs would wave this through at 54s."""
        self._as_exact_backend()
        with mock.patch.object(
            backends, "run_subprocess", self._fixed_length_runner(59.5)
        ):
            with self.assertRaises(core.OutputAuditError) as raised:
                self.gen(model="minimax-mlx", duration=60)
        self.assertEqual(raised.exception.track.audit_status, "short")

    def test_best_effort_contract_still_accepts_an_overlong_render(self):
        """Only an exact contract gains an upper bound; nothing else changes."""
        with mock.patch.object(
            backends, "run_subprocess", self._fixed_length_runner(75)
        ):
            track = self.gen(model="minimax-mlx", duration=60)
        self.assertEqual(track.audit_status, "passed")

    def test_short_output_is_retained_audited_and_rejected(self):
        def short_runner(backend, job):
            path = Path(job["output_path"])
            _write_test_wav(path, frames=20 * 8000)
            return {"path": str(path), "elapsed_seconds": 1.0}

        with mock.patch.object(backends, "run_subprocess", short_runner):
            with self.assertRaises(core.OutputAuditError) as raised:
                self.gen(model="minimax-mlx", duration=240)
        track = raised.exception.track
        sidecar = json.loads(track.sidecar_path().read_text(encoding="utf-8"))
        self.assertTrue(track.path.is_file())
        self.assertEqual(track.audit_status, "short")
        self.assertEqual(track.duration, 20)
        self.assertEqual(track.requested_duration, 240)
        self.assertEqual(sidecar["duration"], 20)
        self.assertEqual(sidecar["requested_duration"], 240)
        self.assertEqual(sidecar["audio_frames"], 160000)
        self.assertIn("Short output retained", str(raised.exception))

    def test_each_backend_enforces_its_own_duration_cap(self):
        for model, duration in (("acestep", 241), ("minimax-mlx", 301), ("musicgen", 31)):
            with self.subTest(model=model), self.assertRaises(ValueError):
                self.gen(model=model, duration=duration)

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

    def test_core_refuses_a_runner_result_without_audio(self):
        with mock.patch.object(
            backends,
            "run_subprocess",
            return_value={"path": "ignored", "elapsed_seconds": 0.1},
        ):
            with self.assertRaisesRegex(RuntimeError, "wrote no audio file"):
                self.gen(model="minimax-mlx")

    def test_output_path_does_not_overwrite_a_same_second_collision(self):
        first = self.out / "same.wav"
        first.write_bytes(b"existing")
        path, reservation = core._reserve_output_path(self.out, "same")
        self.addCleanup(reservation.unlink, missing_ok=True)
        self.assertEqual(path.name, "same_2.wav")

    def test_output_path_reservations_are_atomic_across_concurrent_callers(self):
        barrier = threading.Barrier(8)
        results = []
        lock = threading.Lock()

        def reserve():
            barrier.wait()
            item = core._reserve_output_path(self.out, "concurrent")
            with lock:
                results.append(item)

        threads = [threading.Thread(target=reserve) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(len(results), 8)
        self.assertEqual(len({path for path, _reservation in results}), 8)
        for _path, reservation in results:
            reservation.unlink(missing_ok=True)


class SubprocessContract(unittest.TestCase):
    def setUp(self) -> None:
        self.out = Path(tempfile.mkdtemp()) / "probe.wav"
        self.addCleanup(shutil.rmtree, self.out.parent, ignore_errors=True)
        self.backend = backends.get("minimax-mlx")
        self.job = {"output_path": str(self.out)}

    def _proc(self, stdout: str, returncode: int = 0, stderr: str = ""):
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    def _runner_result(self, payload: dict, *, audio: str = "valid"):
        if audio == "valid":
            _write_test_wav(self.out)
        elif audio == "invalid":
            self.out.write_bytes(b"RIFF")
        elif audio == "empty":
            self.out.touch()
        return self._proc(json.dumps(payload))

    def test_success_requires_matching_path_elapsed_and_valid_audio(self):
        payload = {"path": str(self.out), "elapsed_seconds": 1.25}
        with mock.patch.object(
            backends,
            "_run_process",
            side_effect=lambda *_args: self._runner_result(payload),
        ) as run:
            result = backends.run_subprocess(self.backend, self.job)
        audit = result.pop("_audio_audit")
        self.assertEqual(result, payload)
        self.assertIsInstance(audit, backends.AudioAudit)
        self.assertEqual((audit.frames, audit.sample_rate, audit.channels), (1, 8000, 1))
        self.assertGreater(audit.peak_amplitude, 0)
        self.assertEqual(run.call_args.args[2], self.backend.timeout_seconds)

    def test_silent_audio_is_not_success(self):
        payload = {"path": str(self.out), "elapsed_seconds": 1}

        def silent_result(*_args):
            with wave.open(str(self.out), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\x00\x00" * 8000)
            return self._proc(json.dumps(payload))

        with mock.patch.object(backends, "_run_process", side_effect=silent_result):
            with self.assertRaisesRegex(RuntimeError, "wrote silent audio"):
                backends.run_subprocess(self.backend, self.job)

    def test_non_finite_audio_is_not_success(self):
        payload = {"path": str(self.out), "elapsed_seconds": 1}

        def non_finite_result(*_args):
            sf.write(str(self.out), [float("nan")], 8000, subtype="FLOAT")
            return self._proc(json.dumps(payload))

        with mock.patch.object(backends, "_run_process", side_effect=non_finite_result):
            with self.assertRaisesRegex(RuntimeError, "non-finite audio samples"):
                backends.run_subprocess(self.backend, self.job)

    def test_process_wrapper_uses_strict_utf8_timeout_and_new_session(self):
        proc = mock.Mock(returncode=0)
        proc.communicate.return_value = ("out", "err")
        with mock.patch.object(backends.subprocess, "Popen", return_value=proc) as popen:
            result = backends._run_process(["python", "runner.py"], "{}", 12)
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "strict")
        self.assertEqual(kwargs["start_new_session"], os.name == "posix")
        proc.communicate.assert_called_once_with("{}", timeout=12)
        self.assertEqual((result.stdout, result.stderr), ("out", "err"))

    def test_process_group_probe_permission_error_cannot_escape_cleanup(self):
        proc = mock.Mock(pid=123)
        with mock.patch.object(
            backends.os,
            "killpg",
            side_effect=(None, PermissionError("probe"), ProcessLookupError()),
        ):
            backends._terminate_process_tree(proc)
        proc.wait.assert_called()

    def test_timeout_is_reported_as_a_runner_failure(self):
        with mock.patch.object(
            backends,
            "_run_process",
            side_effect=subprocess.TimeoutExpired("runner", 7200),
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out after 7200 seconds"):
                backends.run_subprocess(self.backend, self.job)

    def test_malformed_or_missing_json_is_reported_cleanly(self):
        for stdout, message in (("{broken", "malformed JSON"), ("chatter", "no JSON")):
            with self.subTest(stdout=stdout), mock.patch.object(
                backends, "_run_process", return_value=self._proc(stdout),
            ):
                with self.assertRaisesRegex(RuntimeError, message):
                    backends.run_subprocess(self.backend, self.job)

    def test_result_contract_rejects_wrong_path_elapsed_or_missing_file(self):
        cases = (
            ({"path": "/wrong.wav", "elapsed_seconds": 1}, "unexpected output path"),
            ({"path": str(self.out), "elapsed_seconds": float("nan")}, "invalid elapsed"),
            ({"path": str(self.out), "elapsed_seconds": 1}, "wrote no audio"),
        )
        for payload, message in cases:
            if self.out.exists():
                self.out.unlink()
            with self.subTest(message=message), mock.patch.object(
                backends,
                "_run_process",
                side_effect=lambda *_args, payload=payload: self._runner_result(
                    payload,
                    audio="valid" if "path" in message or "elapsed" in message else "missing",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, message):
                    backends.run_subprocess(self.backend, self.job)

    def test_empty_output_file_is_not_success(self):
        payload = {"path": str(self.out), "elapsed_seconds": 1}
        with mock.patch.object(
            backends,
            "_run_process",
            side_effect=lambda *_args: self._runner_result(payload, audio="empty"),
        ):
            with self.assertRaisesRegex(RuntimeError, "wrote no audio"):
                backends.run_subprocess(self.backend, self.job)

    def test_invalid_wav_header_is_not_success(self):
        payload = {"path": str(self.out), "elapsed_seconds": 1}
        with mock.patch.object(
            backends,
            "_run_process",
            side_effect=lambda *_args: self._runner_result(payload, audio="invalid"),
        ):
            with self.assertRaisesRegex(RuntimeError, "wrote invalid audio"):
                backends.run_subprocess(self.backend, self.job)

    def test_existing_output_is_refused_before_the_runner_starts(self):
        _write_test_wav(self.out)
        with mock.patch.object(backends, "_run_process") as run:
            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                backends.run_subprocess(self.backend, self.job)
        run.assert_not_called()

    def test_malformed_final_json_cannot_fall_back_to_an_earlier_result(self):
        payload = {"path": str(self.out), "elapsed_seconds": 1}
        stdout = f"{json.dumps(payload)}\n{{broken"
        with mock.patch.object(
            backends, "_run_process", return_value=self._proc(stdout),
        ):
            with self.assertRaisesRegex(RuntimeError, "malformed JSON"):
                backends.run_subprocess(self.backend, self.job)

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX-specific")
    def test_cooperative_timeout_is_reported_and_reaped(self):
        with mock.patch.object(backends, "TERMINATE_GRACE_SECONDS", 0.2):
            with self.assertRaises(subprocess.TimeoutExpired):
                backends._run_process(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    "",
                    0.2,
                )

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX-specific")
    def test_timeout_kills_a_descendant_that_ignores_sigterm(self):
        ready = self.out.parent / "child-ready"
        pid_file = self.out.parent / "child-pid"
        child_code = (
            "import pathlib,signal,time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(ready)!r}).write_text('yes'); "
            "time.sleep(60)"
        )
        parent_code = (
            "import pathlib,subprocess,sys,time; "
            f"child=subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
            f"ready=pathlib.Path({str(ready)!r}); "
            "\nwhile not ready.exists(): time.sleep(0.01)\n"
            f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); "
            "time.sleep(60)"
        )
        with mock.patch.object(backends, "TERMINATE_GRACE_SECONDS", 0.2):
            with self.assertRaises(subprocess.TimeoutExpired):
                backends._run_process([sys.executable, "-c", parent_code], "", 1)
        child_pid = int(pid_file.read_text(encoding="utf-8"))

        def kill_child_if_needed():
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        self.addCleanup(kill_child_if_needed)
        deadline = time.monotonic() + 2
        child_alive = True
        while child_alive and time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                child_alive = False
                break
            time.sleep(0.02)
        self.assertFalse(child_alive, "SIGTERM-ignoring descendant survived group cleanup")

    def test_runtime_probe_imports_declared_modules_with_utf8(self):
        backend = replace(self.backend, probe_modules=("first", "second"))
        with mock.patch.object(
            backends.subprocess,
            "run",
            return_value=self._proc(""),
        ) as run:
            self.assertTrue(backend.available)
        self.assertEqual(
            run.call_args.args[0][-1],
            "import first; import second",
        )
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")

    def test_runtime_probe_failure_marks_backend_missing(self):
        backend = replace(self.backend, probe_modules=("missing_runtime",))
        with mock.patch.object(
            backends.subprocess,
            "run",
            return_value=self._proc("", returncode=1, stderr="ModuleNotFoundError: missing"),
        ):
            self.assertFalse(backend.available)
            self.assertIn("ModuleNotFoundError", backend.availability_error)


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

    def test_uses_current_interpreter_not_a_relocatable_console_script(self):
        cmd = self._run(self._job())
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(Path(cmd[1]).name, "minimax_mlx_runner.py")
        self.assertEqual(cmd[2:4], ["_generate", "generate"])

    def test_requested_duration_is_also_the_minimum_duration(self):
        cmd = self._run(self._job(duration=300))
        self.assertEqual(cmd[cmd.index("--duration") + 1], "300.0")
        self.assertEqual(cmd[cmd.index("--min-duration") + 1], "300.0")

    def test_zero_steps_is_passed_not_dropped(self):
        cmd = self._run(self._job(steps=0))
        self.assertIn("--steps", cmd)

    def test_missing_steps_key_still_works(self):
        job = self._job(); del job["steps"]
        self.assertNotIn("--steps", self._run(job))

    def test_no_guidance_flag_is_ever_sent(self):
        cmd = self._run(self._job())
        self.assertFalse(any("guidance" in c or "cfg" in c for c in cmd))

    def test_fractional_duration_reaches_the_float_cli_without_truncation(self):
        cmd = self._run(self._job(duration=1.5))
        self.assertEqual(cmd[cmd.index("--duration") + 1], "1.5")

    def test_inner_timeout_finishes_before_the_outer_adapter_timeout(self):
        spec = importlib.util.spec_from_file_location(
            "minimax_runner_timeout",
            core.PROJECT_ROOT / "runners" / "minimax_mlx_runner.py",
        )
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        self.assertLess(
            runner.COMMAND_TIMEOUT_SECONDS,
            backends.get("minimax-mlx").timeout_seconds,
        )


class MinimaxMinimumDurationWrapper(unittest.TestCase):
    def _load(self):
        spec = importlib.util.spec_from_file_location(
            "minimax_min_duration",
            core.PROJECT_ROOT / "runners" / "minimax_mlx_runner.py",
        )
        wrapper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wrapper)
        return wrapper

    def test_wrapper_flag_is_removed_before_upstream_cli(self):
        wrapper = self._load()
        minimum, forwarded = wrapper._parse_wrapper_args([
            "generate", "--duration", "300", "--min-duration", "300",
        ])
        self.assertEqual(minimum, 300)
        self.assertEqual(forwarded, ["generate", "--duration", "300"])

    def test_invalid_minimum_duration_is_rejected(self):
        wrapper = self._load()
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                wrapper._parse_wrapper_args(["--min-duration", value])

    def test_stop_token_is_masked_until_minimum_frames_are_complete(self):
        wrapper = self._load()
        import types
        import numpy as np

        sampled_vocabularies = []

        def original_guidance(logits, allowed_vocab, cfg_scale=1.5, conditional_top_k=50):
            sampled_vocabularies.append(np.array(allowed_vocab, copy=True))
            return logits

        mlx = types.ModuleType("mlx")
        mlx_core = types.ModuleType("mlx.core")
        mlx_core.arange = np.arange
        mlx_core.where = np.where
        mlx_core.inf = np.inf
        mlx.core = mlx_core

        package = types.ModuleType("mlx_minimax_music3")
        pipeline = types.ModuleType("mlx_minimax_music3.pipeline")
        pipeline.semantic_guided_logits = original_guidance
        config = types.ModuleType("mlx_minimax_music3.config")

        class ModelConfig:
            audio_end_token_id = 4

        class GenerationConfig:
            def __init__(self, audio_duration):
                self.audio_duration = audio_duration

            def max_frames(self, model):
                return 2

        config.ModelConfig = ModelConfig
        config.GenerationConfig = GenerationConfig
        package.pipeline = pipeline

        fake_modules = {
            "mlx": mlx,
            "mlx.core": mlx_core,
            "mlx_minimax_music3": package,
            "mlx_minimax_music3.pipeline": pipeline,
            "mlx_minimax_music3.config": config,
        }
        with mock.patch.dict(sys.modules, fake_modules):
            self.assertEqual(wrapper._install_minimum_duration(2), 2)
            logits = np.zeros((2, 6))
            allowed = np.ones(6, dtype=bool)
            for _ in range(4):
                pipeline.semantic_guided_logits(logits, allowed)

        for call in sampled_vocabularies[:3]:
            self.assertFalse(call[4])
        self.assertTrue(sampled_vocabularies[3][4])


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

    def test_each_backend_owns_its_numeric_control_contract(self):
        self.assertEqual(backends.get("acestep").duration.maximum, 240)
        self.assertEqual(backends.get("minimax-mlx").duration.maximum, 300)
        self.assertEqual(backends.get("musicgen").duration.maximum, 30)
        self.assertIsNone(backends.get("musicgen").steps)
        self.assertIsNone(backends.get("minimax-mlx").guidance)

    def test_minimax_probes_the_exact_cli_module_it_invokes(self):
        self.assertEqual(
            backends.get("minimax-mlx").probe_modules,
            ("mlx_minimax_music3.cli",),
        )

    def test_control_validation_rejects_non_finite_fractional_and_out_of_range_values(self):
        with self.assertRaises(ValueError):
            backends.get("minimax-mlx").duration.validate(float("inf"), "duration")
        with self.assertRaises(ValueError):
            backends.get("minimax-mlx").steps.validate(3.5, "steps")
        with self.assertRaises(ValueError):
            backends.get("acestep").guidance.validate(31, "guidance")

    def test_manifest_declares_the_default_and_every_registered_backend(self):
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(document["schema_version"], 5)
        self.assertEqual(document["default_backend"], backends.DEFAULT_BACKEND)
        self.assertEqual(backends.DEFAULT_BACKEND, "minimax-mlx")
        self.assertEqual(list(document["backends"]), list(backends.BACKENDS))

    def test_every_backend_declares_a_valid_output_audit_policy(self):
        for backend in backends.BACKENDS.values():
            with self.subTest(backend=backend.name):
                self.assertGreater(backend.output_audit.minimum_duration_ratio, 0)
                self.assertLessEqual(backend.output_audit.minimum_duration_ratio, 1)
                self.assertGreaterEqual(backend.output_audit.duration_tolerance_seconds, 0)
                self.assertGreaterEqual(backend.output_audit.random_seed_retries, 0)
        self.assertEqual(backends.get("minimax-mlx").output_audit.minimum_duration(240), 216)
        self.assertEqual(backends.get("minimax-mlx").output_audit.minimum_duration(1), 0.9)

    def test_manifest_rejects_invalid_output_audit_policy(self):
        cases = (
            ("minimum_duration_ratio", 0, "within"),
            ("minimum_duration_ratio", float("nan"), "within"),
            ("duration_tolerance_seconds", -1, "non-negative"),
            ("random_seed_retries", True, "non-negative integer"),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
                document["backends"]["minimax-mlx"]["output_audit"][field] = value
                path = Path(tempfile.mkdtemp()) / "backends.json"
                self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    backends.load_manifest(path)

    def test_runner_options_reach_the_runner_job_unchanged(self):
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        document["backends"]["minimax-mlx"]["runtime"]["runner_options"] = {
            "dit": "sm-music",
            "decoder": "same-s",
        }
        path = Path(tempfile.mkdtemp()) / "backends.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        _default, loaded = backends.load_manifest(path)
        self.assertEqual(
            dict(loaded["minimax-mlx"].runner_options),
            {"dit": "sm-music", "decoder": "same-s"},
        )

    def test_a_backend_stays_hashable_with_runner_options(self):
        """Backend is a frozen value object; a dict field would silently break that."""
        options = {"dit": "medium"}
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        document["backends"]["minimax-mlx"]["runtime"]["runner_options"] = options
        path = Path(tempfile.mkdtemp()) / "backends.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        _default, loaded = backends.load_manifest(path)
        self.assertIsInstance(hash(loaded["minimax-mlx"]), int)

    def test_manifest_rejects_unusable_runner_options(self):
        cases = (
            ({"dit": 3}, "non-empty strings"),
            ({"dit": ""}, "non-empty strings"),
            ({"": "sm-music"}, "non-empty strings"),
            ("sm-music", "non-empty strings"),
        )
        for value, message in cases:
            with self.subTest(value=value):
                document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
                document["backends"]["minimax-mlx"]["runtime"]["runner_options"] = value
                path = Path(tempfile.mkdtemp()) / "backends.json"
                self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    backends.load_manifest(path)

    def test_runner_options_are_refused_without_a_runner(self):
        """An in-process backend never sees a job dict, so options there are a lie."""
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        document["backends"]["acestep"]["runtime"]["runner_options"] = {"dit": "medium"}
        path = Path(tempfile.mkdtemp()) / "backends.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "needs a runner to receive them"):
            backends.load_manifest(path)

    def test_manifest_rejects_an_unknown_duration_contract(self):
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        document["backends"]["minimax-mlx"]["output_audit"]["duration_contract"] = "whenever"
        path = Path(tempfile.mkdtemp()) / "backends.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be one of"):
            backends.load_manifest(path)

    def test_exact_contract_cannot_also_accept_or_retry_a_wrong_length(self):
        """An exact contract claims the length is guaranteed, so the same manifest
        entry must not simultaneously describe a short result as acceptable, ask for
        a retry that can only reproduce the same length, or demand bit-exactness that
        sample-rate rounding cannot deliver."""
        base = {
            "minimum_duration_ratio": 1,
            "duration_tolerance_seconds": 0.05,
            "random_seed_retries": 0,
            "duration_contract": "exact",
        }
        self.assertEqual(
            backends.OutputAuditPolicy.from_manifest(base, "probe").duration_contract,
            "exact",
        )
        cases = (
            ({"minimum_duration_ratio": 0.9}, "must be 1 under an exact contract"),
            ({"random_seed_retries": 1}, "must be 0 under an exact contract"),
            ({"duration_tolerance_seconds": 0}, "must be positive under an exact"),
        )
        for override, message in cases:
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, message):
                    backends.OutputAuditPolicy.from_manifest({**base, **override}, "probe")

    def test_only_an_exact_contract_bounds_the_delivered_duration_from_above(self):
        best_effort = backends.get("minimax-mlx").output_audit
        self.assertEqual(best_effort.duration_contract, "best_effort")
        self.assertEqual(best_effort.maximum_duration(240), math.inf)
        exact = backends.OutputAuditPolicy.from_manifest(
            {
                "minimum_duration_ratio": 1,
                "duration_tolerance_seconds": 0.05,
                "random_seed_retries": 0,
                "duration_contract": "exact",
            },
            "probe",
        )
        self.assertAlmostEqual(exact.maximum_duration(240), 240.05)
        self.assertAlmostEqual(exact.minimum_duration(240), 239.95)

    def test_every_backend_declares_a_known_duration_contract(self):
        for backend in backends.BACKENDS.values():
            with self.subTest(backend=backend.name):
                self.assertIn(
                    backend.output_audit.duration_contract, backends.DURATION_CONTRACTS
                )

    def test_new_manifest_backend_gets_runtime_and_ui_settings_without_python_edits(self):
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        probe = json.loads(json.dumps(document["backends"]["minimax-mlx"]))
        probe["model_id"] = "example/probe-model"
        probe["runner"] = "probe_runner.py"
        probe["controls"]["duration"]["maximum"] = 123
        document["backends"]["probe"] = probe
        path = Path(tempfile.mkdtemp()) / "backends.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(document), encoding="utf-8")

        default, loaded = backends.load_manifest(path)

        self.assertEqual(default, "minimax-mlx")
        self.assertEqual(loaded["probe"].model_id, "example/probe-model")
        self.assertEqual(loaded["probe"].duration.maximum, 123)
        self.assertEqual(loaded["probe"].steps.default, 30)

    def test_manifest_rejects_unknown_fields_instead_of_silently_dropping_them(self):
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        document["backends"]["acestep"]["mystery_setting"] = True
        path = Path(tempfile.mkdtemp()) / "backends.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown fields: mystery_setting"):
            backends.load_manifest(path)

    def test_manifest_rejects_non_finite_numeric_control_fields(self):
        for field, value in (
            ("default", float("nan")),
            ("minimum", float("-inf")),
            ("maximum", float("inf")),
            ("step", float("nan")),
        ):
            with self.subTest(field=field):
                document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
                document["backends"]["minimax-mlx"]["controls"]["duration"][field] = value
                path = Path(tempfile.mkdtemp()) / "backends.json"
                self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "must be a finite number"):
                    backends.load_manifest(path)

    def test_manifest_rejects_booleans_and_wrong_numeric_field_types(self):
        for field, value in (
            ("default", True),
            ("minimum", "1"),
            ("maximum", False),
            ("step", "1"),
        ):
            with self.subTest(field=field):
                document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
                document["backends"]["minimax-mlx"]["controls"]["duration"][field] = value
                path = Path(tempfile.mkdtemp()) / "backends.json"
                self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "must be a finite number"):
                    backends.load_manifest(path)

    def test_manifest_requires_runtime_probe_and_timeout_for_subprocess_models(self):
        document = json.loads(backends.MANIFEST_PATH.read_text(encoding="utf-8"))
        document["backends"]["minimax-mlx"]["runtime"]["timeout_seconds"] = None
        path = Path(tempfile.mkdtemp()) / "backends.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "timeout_seconds is required"):
            backends.load_manifest(path)


class AnalysisHonesty(unittest.TestCase):
    def _result(self, name: str = "good") -> analyze.Analysis:
        return analyze.Analysis(
            name=name,
            duration=10.0,
            tempo=90.0,
            target_collection=None,
            pitch_coverage=None,
            peak_pitch="D",
            hit_alignment=0.5,
            quiet_start=False,
            quiet_end=False,
        )

    def test_scale_fit_is_opt_in_not_hardcoded_to_d_mixolydian(self):
        pitches, label = analyze._target_pitch_classes(None, None)
        self.assertIsNone(pitches)
        self.assertIsNone(label)
        pitches, label = analyze._target_pitch_classes("D", "mixolydian")
        self.assertEqual(pitches, {0, 2, 4, 6, 7, 9, 11})
        self.assertEqual(label, "D mixolydian")
        self.assertEqual(
            analyze._target_pitch_classes("db", "major"),
            analyze._target_pitch_classes("Db", "major"),
        )

    def test_key_and_scale_must_be_supplied_together(self):
        with self.assertRaisesRegex(ValueError, "supplied together"):
            analyze._target_pitch_classes("D", None)
        with self.assertRaisesRegex(ValueError, "unknown scale"):
            analyze._target_pitch_classes("D", "invented")

    def test_short_clip_uses_at_least_one_rms_frame(self):
        self.assertEqual(
            analyze._quiet_edge_flags(analyze.np.array([0.1, 1.0, 1.0])),
            (True, False),
        )
        self.assertEqual(
            analyze._quiet_edge_flags(analyze.np.array([float("nan")])),
            (False, False),
        )
        self.assertEqual(analyze._quiet_edge_flags(analyze.np.array([])), (False, False))

    def test_line_does_not_invent_a_scale_score_without_a_target(self):
        line = self._result().line()
        self.assertIn("--", line)
        self.assertNotIn("Mixolydian", line)

    def test_complete_path_leaves_non_finite_measurements_unscored(self):
        fake_librosa = SimpleNamespace(
            load=lambda *_args, **_kwargs: (analyze.np.ones(300), 10),
            beat=SimpleNamespace(
                beat_track=lambda **_kwargs: (analyze.np.array([float("nan")]), []),
            ),
            feature=SimpleNamespace(
                chroma_cqt=lambda **_kwargs: analyze.np.full((12, 2), float("nan")),
                rms=lambda **_kwargs: analyze.np.array([[float("nan")]]),
            ),
            onset=SimpleNamespace(
                onset_strength=lambda **_kwargs: analyze.np.full(30, float("nan")),
            ),
            times_like=lambda values, **_kwargs: analyze.np.arange(len(values)),
        )
        with mock.patch.dict(sys.modules, {"librosa": fake_librosa}):
            result = analyze.analyse(Path("silent.wav"), key="d", scale="mixolydian")
        self.assertIsNone(result.tempo)
        self.assertIsNone(result.pitch_coverage)
        self.assertEqual(result.peak_pitch, "--")
        self.assertIsNone(result.hit_alignment)
        self.assertFalse(result.quiet_start)
        self.assertFalse(result.quiet_end)
        self.assertIn("hits  --", result.line())

    def test_import_does_not_hide_runtime_warnings_by_default(self):
        probe = (
            "import warnings; from synth import analyze; "
            "warnings.warn('visible-analysis-warning', RuntimeWarning)"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=core.PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("visible-analysis-warning", result.stderr)

    def test_complete_path_rejects_loaded_audio_with_no_samples(self):
        fake_librosa = SimpleNamespace(load=lambda *_args, **_kwargs: (analyze.np.array([]), 8000))
        with mock.patch.dict(sys.modules, {"librosa": fake_librosa}):
            with self.assertRaisesRegex(ValueError, "no samples"):
                analyze.analyse(Path("empty.wav"))

    def test_one_bad_file_does_not_abort_the_remaining_batch(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            analyze,
            "analyse",
            side_effect=(OSError("broken wav"), self._result()),
        ) as analyse_track, mock.patch.object(sys, "stdout", stdout), mock.patch.object(
            sys, "stderr", stderr,
        ):
            result = analyze.main(["bad.wav", "good.wav"])
        self.assertEqual(result, 1)
        self.assertIn("bad.wav: failed: broken wav", stderr.getvalue())
        self.assertIn("good", stdout.getvalue())
        self.assertIn("peak", stdout.getvalue().splitlines()[0])
        self.assertNotIn("tonic", stdout.getvalue().splitlines()[0])
        self.assertIn("edges", stdout.getvalue().splitlines()[0])
        self.assertNotIn("sweeps", stdout.getvalue().splitlines()[0])
        self.assertEqual(analyse_track.call_count, 2)

    def test_main_passes_an_explicit_target_to_every_file(self):
        with mock.patch.object(analyze, "analyse", return_value=self._result()) as analyse_track, \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(
                analyze.main(["track.wav", "--key", "D", "--scale", "mixolydian"]),
                0,
            )
        analyse_track.assert_called_once_with(
            Path("track.wav"), 8.0, "D", "mixolydian",
        )


class GenerationQueueTests(unittest.TestCase):
    def test_jobs_run_serially_and_pending_jobs_can_move_or_be_removed(self):
        first_started = threading.Event()
        release_first = threading.Event()
        order = []
        output = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, output, ignore_errors=True)

        def run(payload):
            order.append(payload["name"])
            if payload["name"] == "first":
                first_started.set()
                self.assertTrue(release_first.wait(2))
            path = output / f"{payload['name']}.wav"
            path.write_bytes(b"RIFF")
            return SimpleNamespace(path=path)

        queue = jobs.GenerationQueue(run, completed_hold_seconds=10)
        self.addCleanup(queue.stop)
        first = queue.enqueue({"name": "first"}, {"name": "first"}, 10)
        self.assertTrue(first_started.wait(1))
        second = queue.enqueue({"name": "second"}, {"name": "second"}, 10)
        third = queue.enqueue({"name": "third"}, {"name": "third"}, 10)

        after_active_remove = queue.remove(first["id"])
        self.assertEqual(after_active_remove[0]["status"], "running")

        queue.move(third["id"], -1)
        queued = [item["name"] for item in queue.snapshot() if item["status"] == "queued"]
        self.assertEqual(queued, ["third", "second"])
        queue.remove(second["id"])
        release_first.set()

        deadline = time.monotonic() + 2
        while order != ["first", "third"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(order, ["first", "third"])

    def test_running_progress_is_explicitly_estimated_and_capped(self):
        now = [0.0]
        started = threading.Event()
        release = threading.Event()
        output = Path(tempfile.mkdtemp()) / "probe.wav"
        self.addCleanup(shutil.rmtree, output.parent, ignore_errors=True)

        def run(_payload):
            started.set()
            self.assertTrue(release.wait(2))
            output.write_bytes(b"RIFF")
            return SimpleNamespace(path=output)

        queue = jobs.GenerationQueue(run, clock=lambda: now[0])
        self.addCleanup(queue.stop)
        queue.enqueue({}, {"name": "probe"}, expected_seconds=10)
        self.assertTrue(started.wait(1))
        now[0] = 5
        running = queue.snapshot()[0]
        self.assertEqual((running["status"], running["progress"]), ("running", 45.0))
        now[0] = 50
        self.assertEqual(queue.snapshot()[0]["progress"], 95.0)
        release.set()

    def test_missing_output_is_a_visible_failed_job(self):
        queue = jobs.GenerationQueue(
            lambda _payload: SimpleNamespace(path=Path("/missing.wav")),
        )
        self.addCleanup(queue.stop)
        queue.enqueue({}, {"name": "missing"}, expected_seconds=10)
        deadline = time.monotonic() + 1
        snapshot = queue.snapshot()
        while snapshot[0]["status"] != "failed" and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = queue.snapshot()
        self.assertEqual(snapshot[0]["status"], "failed")
        self.assertIn("without writing its WAV", snapshot[0]["error"])

    def test_completed_job_reflects_the_seed_and_duration_that_passed_audit(self):
        output = Path(tempfile.mkdtemp()) / "accepted.wav"
        self.addCleanup(shutil.rmtree, output.parent, ignore_errors=True)

        def run(_payload):
            output.write_bytes(b"RIFF")
            return SimpleNamespace(path=output, seed=99, duration=238.5)

        queue = jobs.GenerationQueue(run, completed_hold_seconds=10)
        self.addCleanup(queue.stop)
        queue.enqueue({}, {"seed": 42, "duration": 240}, expected_seconds=10)
        deadline = time.monotonic() + 1
        snapshot = queue.snapshot()
        while snapshot[0]["status"] != "complete" and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = queue.snapshot()
        self.assertEqual(snapshot[0]["seed"], 99)
        self.assertEqual(snapshot[0]["delivered_duration"], 238.5)


class UiHistory(unittest.TestCase):
    def setUp(self) -> None:
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def _track(self, name: str, modified: int, metadata: dict | str | None = None) -> Path:
        path = self.out / f"{name}.wav"
        _write_test_wav(path, frames=8000)
        os.utime(path, ns=(modified, modified))
        if isinstance(metadata, dict):
            path.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
        elif isinstance(metadata, str):
            path.with_suffix(".json").write_text(metadata, encoding="utf-8")
        return path

    def test_history_is_newest_first_and_only_contains_wavs(self):
        self._track("older", 10)
        self._track("newer", 20)
        (self.out / "newest.json").write_text("{}", encoding="utf-8")
        self.assertEqual(
            [track["name"] for track in app._load_history(self.out)],
            ["newer.wav", "older.wav"],
        )

    def test_history_refreshes_when_a_sidecar_arrives_after_its_wav(self):
        path = self._track("still-writing", 10)
        before = app._history_signature(self.out)
        path.with_suffix(".json").write_text(
            json.dumps({"backend": "minimax-mlx"}), encoding="utf-8",
        )
        after = app._history_signature(self.out)
        self.assertNotEqual(before, after)

    def test_missing_or_malformed_sidecars_do_not_hide_creative_assets(self):
        self._track("missing", 10)
        self._track("malformed", 20, "not json")
        tracks = app._load_history(self.out)
        self.assertEqual(len(tracks), 2)
        self.assertTrue(all(track["backend"] == "unknown model" for track in tracks))

    def test_invalid_sidecar_values_do_not_break_history_copy(self):
        self._track("invalid-values", 10, {"duration": {"not": "a number"}})
        copy = app._history_copy(app._load_history(self.out)[0])
        self.assertIn("invalid-values.wav", copy)

        self._track("overflow", 20, {"duration": 10 ** 1000})
        copy = app._history_copy(app._load_history(self.out)[0])
        self.assertIn("overflow.wav", copy)

    def test_history_uses_sidecar_details_when_present(self):
        self._track("complete", 10, {
            "backend": "minimax-mlx",
            "duration": 45,
            "seed": 123,
            "prompt": "probe",
            "generated_at": "20260915-120000",
        })
        track = app._load_history(self.out)[0]
        self.assertEqual((track["backend"], track["seed"]), ("minimax-mlx", 123))
        self.assertEqual(track["duration"], 1)
        self.assertEqual(track["requested_duration"], 45)
        self.assertEqual(track["audit_status"], "short")
        copy = app._history_copy(track)
        self.assertIn("1.0s delivered", copy)
        self.assertIn("45s target", copy)
        self.assertIn("SHORT", copy)

    def test_history_does_not_call_a_long_silent_file_passed(self):
        path = self.out / "silent.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\x00\x00" * 10 * 8000)
        path.with_suffix(".json").write_text(
            json.dumps({"backend": "minimax-mlx", "duration": 10}),
            encoding="utf-8",
        )
        track = app._load_history(self.out)[0]
        self.assertIsNone(track["duration"])
        self.assertEqual(track["audit_status"], "invalid")
        self.assertIn("silent audio", track["audit_error"])
        self.assertIn("INVALID", app._history_copy(track))

    def test_history_waveform_contains_every_peak_and_is_seekable(self):
        track = {
            "path": str(self.out / "probe.wav"),
            "name": 'probe & "seek".wav',
            "modified_ns": 10,
        }
        with mock.patch.object(app, "_waveform_peaks", return_value=(0.2, 1.0, 0.5)):
            waveform = app._history_waveform(track)
        self.assertEqual(waveform.count("<rect "), 3)
        self.assertIn('role="slider"', waveform)
        self.assertIn("probe &amp; &quot;seek&quot;.wav", waveform)


class UiModelSelection(unittest.TestCase):
    def test_generation_button_acknowledges_click_and_recovers(self):
        started = app._generation_started()
        self.assertEqual(started["value"], "Generating...")
        self.assertFalse(started["interactive"])
        finished = app._generation_finished()
        self.assertEqual(finished["value"], "Generate")
        self.assertTrue(finished["interactive"])

    def test_generation_progress_fills_button_and_waveforms_fit_without_scrolling(self):
        self.assertIn("#generate-button:disabled::before", app.UI_CSS)
        self.assertIn("inset: 0;", app.UI_CSS)
        self.assertIn(".queue-job.queued .queue-job-fill", app.UI_CSS)
        self.assertIn("animation: queued-job-wipe 1.4s ease-in-out infinite;", app.UI_CSS)
        self.assertIn(".history-audio .waveform-container", app.UI_CSS)
        self.assertIn(
            ".history-audio .subtitle-display {\n    display: none;\n}",
            app.UI_CSS,
        )
        self.assertIn('document.addEventListener("click"', app.UI_JS)
        self.assertIn("audio.currentTime = Math.max", app.UI_JS)

    def test_queue_cards_distinguish_waiting_from_estimated_render_progress(self):
        base = {
            "id": "job-1",
            "model": "minimax-mlx",
            "duration": 60,
            "seed": 123,
            "prompt": "quiet & focused",
            "error": None,
        }
        queued = app._queue_job_html({
            **base, "status": "queued", "progress": 0, "queue_position": 2,
        })
        running = app._queue_job_html({
            **base, "status": "running", "progress": 45,
        })
        self.assertIn('class="queue-job queued"', queued)
        self.assertIn("Queued #2", queued)
        self.assertIn("quiet &amp; focused", queued)
        self.assertIn("Rendering · estimated 45%", running)
        self.assertIn("--job-progress: 45%", running)

    def test_switching_to_musicgen_clamps_duration_and_hides_steps(self):
        updates = app._model_updates("musicgen", 60, None)
        self.assertEqual(updates[1]["value"], 30)
        self.assertEqual(updates[1]["maximum"], 30)
        self.assertFalse(updates[2]["visible"])
        self.assertEqual(updates[3]["value"], 3.0)

    def test_switching_to_minimax_exposes_its_full_duration_and_only_its_controls(self):
        updates = app._model_updates("minimax-mlx", 270, None)
        self.assertEqual((updates[1]["value"], updates[1]["maximum"]), (270, 300))
        self.assertEqual(updates[2]["value"], 30)
        self.assertIsNone(updates[2]["maximum"])
        self.assertFalse(updates[3]["visible"])

    def test_minimax_presets_are_structured_captions(self):
        prompt = app._preset_prompt("Lo-fi / relaxed", "minimax-mlx")
        self.assertIn("Genre: lo-fi hip hop", prompt)
        self.assertIn("BPM: 85", prompt)
        self.assertIn("Arrangement:", prompt)

    def test_ui_build_wires_model_change_history_refresh_and_generation(self):
        probe = """
import json
import app

config = app.build_ui().get_config_file()
components = {component["id"]: component for component in config["components"]}
model_id = next(
    component_id for component_id, component in components.items()
    if component["type"] == "dropdown" and component["props"].get("label") == "Model"
)
duration_id = next(
    component_id for component_id, component in components.items()
    if component["type"] == "slider" and component["props"].get("label") == "Target duration (s)"
)
guidance_id = next(
    component_id for component_id, component in components.items()
    if component["type"] == "slider" and component["props"].get("label") == "Prompt adherence"
)
generate_id = next(
    component_id for component_id, component in components.items()
    if component["type"] == "button" and component["props"].get("value") == "Generate"
)
submission = next(
    dependency for dependency in config["dependencies"]
    if dependency.get("api_name") == "_enqueue_generation"
)
submission_id = submission["id"]
print(json.dumps({
    "models": [value for _label, value in components[model_id]["props"]["choices"]],
    "default_model": components[model_id]["props"].get("value"),
    "default_guidance_visible": components[guidance_id]["props"].get("visible", True),
    "duration_api_maximum": components[duration_id]["props"].get("maximum"),
    "buttons": [
        component["props"].get("value") for component in components.values()
        if component["type"] == "button"
    ],
    "model_change": any(
        dependency["targets"] == [(model_id, "change")]
        for dependency in config["dependencies"]
    ),
    "model_load": any(
        any(target[1] == "load" for target in dependency["targets"])
        for dependency in config["dependencies"]
    ),
    "render_count": sum(
        dependency.get("render_id") is not None for dependency in config["dependencies"]
    ),
    "queue_poll": any(
        dependency.get("api_name") == "_poll_ui"
        for dependency in config["dependencies"]
    ),
    "submission_outputs_queue": len(submission["outputs"]) == 3,
    "button_success_recovery": any(
        dependency["outputs"] == [generate_id]
        and dependency.get("trigger_after") == submission_id
        and dependency.get("trigger_only_on_success")
        for dependency in config["dependencies"]
    ),
    "button_failure_recovery": any(
        dependency["outputs"] == [generate_id]
        and dependency.get("trigger_after") == submission_id
        and dependency.get("trigger_only_on_failure")
        for dependency in config["dependencies"]
    ),
    "panel_scales": {
        component["props"].get("elem_id"): component["props"].get("scale")
        for component in components.values()
        if component["props"].get("elem_id") in {"controls-panel", "history-panel"}
    },
}))
"""
        result = subprocess.run(
            [sys.executable, "-c", probe], cwd=core.PROJECT_ROOT,
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["models"], list(backends.BACKENDS))
        self.assertEqual(config["default_model"], "minimax-mlx")
        self.assertFalse(config["default_guidance_visible"])
        self.assertEqual(config["duration_api_maximum"], 300)
        self.assertIn("Generate", config["buttons"])
        self.assertIn("Refresh history", config["buttons"])
        self.assertTrue(config["model_change"])
        self.assertTrue(config["model_load"])
        self.assertGreaterEqual(config["render_count"], 2)
        self.assertTrue(config["queue_poll"])
        self.assertTrue(config["submission_outputs_queue"])
        self.assertTrue(config["button_success_recovery"])
        self.assertTrue(config["button_failure_recovery"])
        self.assertEqual(
            config["panel_scales"],
            {"controls-panel": 1, "history-panel": 1},
        )

    def test_new_browser_sessions_load_fresh_server_owned_queue_and_history(self):
        with mock.patch.object(app, "_queue_snapshot", return_value=["job"]), \
                mock.patch.object(app, "_load_history", return_value=["track"]):
            self.assertEqual(app._queue_items_for_render(["stale job"]), ["job"])
            self.assertEqual(app._history_items_for_render(["stale track"]), ["track"])

    def test_concurrent_first_access_creates_one_server_queue(self):
        previous_queue = app._JOB_QUEUE
        app._JOB_QUEUE = None
        self.addCleanup(setattr, app, "_JOB_QUEUE", previous_queue)
        first_constructor_entered = threading.Event()
        release_first_constructor = threading.Event()
        second_caller_reached_boundary = threading.Event()
        created = []
        created_lock = threading.Lock()

        class ObservedLock:
            def __init__(self):
                self.lock = threading.Lock()
                self.entry_count = 0
                self.entry_count_lock = threading.Lock()

            def __enter__(self):
                with self.entry_count_lock:
                    self.entry_count += 1
                    if self.entry_count == 2:
                        second_caller_reached_boundary.set()
                self.lock.acquire()
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                self.lock.release()

        def construct(_runner):
            queue = object()
            with created_lock:
                index = len(created)
                created.append(queue)
            if index == 0:
                first_constructor_entered.set()
                release_first_constructor.wait(timeout=1)
            else:
                # Only the lock-removal mutation can reach a second constructor.
                second_caller_reached_boundary.set()
            return queue

        returned = []
        with mock.patch.object(app, "_JOB_QUEUE_LOCK", ObservedLock()), \
                mock.patch.object(app.jobs, "GenerationQueue", side_effect=construct):
            first = threading.Thread(target=lambda: returned.append(app._get_job_queue()))
            second = threading.Thread(target=lambda: returned.append(app._get_job_queue()))
            first.start()
            self.assertTrue(first_constructor_entered.wait(timeout=1))
            second.start()
            try:
                self.assertTrue(second_caller_reached_boundary.wait(timeout=1))
            finally:
                release_first_constructor.set()
            first.join(timeout=1)
            second.join(timeout=1)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(created), 1)
        self.assertEqual(returned, [created[0], created[0]])

    def test_enqueue_captures_selected_backend_and_returns_button_immediately(self):
        queue = mock.Mock()
        queue.enqueue.return_value = {"id": "job-1"}
        queue.snapshot.return_value = [{"id": "job-1", "status": "queued"}]
        with mock.patch.object(app, "_get_job_queue", return_value=queue), \
                mock.patch.object(app, "_estimate_runtime", return_value=90), \
                mock.patch.object(app.random, "randint", return_value=123):
            status, seed, snapshot = app._enqueue_generation(
                "acestep", " probe ", 120, 60, 15, 42, False,
            )
        payload, summary, expected = queue.enqueue.call_args.args
        self.assertEqual(payload["model"], "acestep")
        self.assertEqual(payload["prompt"], "probe")
        self.assertEqual(payload["duration"], 120)
        self.assertEqual(payload["guidance_scale"], 15)
        self.assertEqual(payload["seed"], 123)
        self.assertEqual(payload["_duration_retries"], 1)
        self.assertTrue(payload["_retry_seed"])
        self.assertEqual((summary["model"], expected), ("acestep", 90))
        self.assertEqual((seed, snapshot[0]["status"]), (123, "queued"))
        self.assertIn("ready for another job", status)

    def test_duration_audit_retries_once_with_a_new_seed(self):
        short_track = SimpleNamespace(
            backend="minimax-mlx",
            duration=20,
            requested_duration=240,
            path=Path("short.wav"),
        )
        short_error = core.OutputAuditError(short_track, 215)
        accepted = SimpleNamespace(path=Path("accepted.wav"), seed=99)
        payload = {
            "model": "minimax-mlx",
            "prompt": "probe",
            "duration": 240,
            "seed": 42,
            "infer_step": 30,
            "guidance_scale": None,
            "_duration_retries": 1,
            "_retry_seed": True,
        }
        with mock.patch.object(core, "generate", side_effect=(short_error, accepted)) as generate, \
                mock.patch.object(app.random, "randint", return_value=99):
            self.assertIs(app._run_queued_job(payload), accepted)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(generate.call_args_list[0].kwargs["seed"], 42)
        self.assertEqual(generate.call_args_list[1].kwargs["seed"], 99)
        self.assertNotIn("_duration_retries", generate.call_args_list[0].kwargs)

    def test_fixed_seed_does_not_retry_a_short_output(self):
        short_track = SimpleNamespace(
            backend="minimax-mlx",
            duration=20,
            requested_duration=240,
            path=Path("short.wav"),
        )
        payload = {
            "model": "minimax-mlx",
            "prompt": "probe",
            "duration": 240,
            "seed": 42,
            "_duration_retries": 0,
            "_retry_seed": False,
        }
        with mock.patch.object(
            core, "generate", side_effect=core.OutputAuditError(short_track, 215),
        ) as generate:
            with self.assertRaisesRegex(RuntimeError, "after 1 attempt"):
                app._run_queued_job(payload)
        generate.assert_called_once()

    def test_twice_short_retry_updates_the_failed_queue_card_seed(self):
        output = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, output, ignore_errors=True)

        def fail_for_seed(**request):
            track = SimpleNamespace(
                backend="minimax-mlx",
                duration=20,
                requested_duration=240,
                path=output / f"short-seed-{request['seed']}.wav",
                seed=request["seed"],
            )
            raise core.OutputAuditError(track, 216)

        payload = {
            "model": "minimax-mlx",
            "prompt": "probe",
            "duration": 240,
            "seed": 42,
            "_duration_retries": 1,
            "_retry_seed": True,
        }
        with mock.patch.object(core, "generate", side_effect=fail_for_seed), \
                mock.patch.object(app.random, "randint", return_value=99):
            queue = jobs.GenerationQueue(app._run_queued_job)
            self.addCleanup(queue.stop)
            queue.enqueue(payload, {"seed": 42, "duration": 240}, expected_seconds=10)
            deadline = time.monotonic() + 1
            snapshot = queue.snapshot()
            while snapshot[0]["status"] != "failed" and time.monotonic() < deadline:
                time.sleep(0.01)
                snapshot = queue.snapshot()
        self.assertEqual(snapshot[0]["seed"], 99)
        self.assertIn("after 2 attempts", snapshot[0]["error"])

    def test_enqueue_rejects_non_finite_and_non_positive_durations(self):
        for duration in (float("nan"), float("inf"), 0, -1):
            with self.subTest(duration=duration), self.assertRaises(app.gr.Error):
                app._enqueue_generation(
                    "acestep", "probe", duration, 60, 15, 42, True,
                )

    def test_enqueue_enforces_the_selected_backend_not_the_default_backend(self):
        for model, duration in (("acestep", 241), ("minimax-mlx", 301), ("musicgen", 31)):
            with self.subTest(model=model), self.assertRaises(app.gr.Error):
                app._enqueue_generation(model, "probe", duration, 60, 15, 42, True)

    def test_enqueue_rejects_model_specific_control_values(self):
        for steps, guidance in ((3.5, 15), (201, 15), (60, 31)):
            with self.subTest(steps=steps, guidance=guidance), self.assertRaises(app.gr.Error):
                app._enqueue_generation("acestep", "probe", 60, steps, guidance, 42, True)

    def test_runtime_estimate_ignores_non_finite_history_metadata(self):
        corrupt = [{
            "backend": "minimax-mlx",
            "duration": 60,
            "elapsed_seconds": float("inf"),
        }]
        with mock.patch.object(app, "_load_history", return_value=corrupt):
            self.assertEqual(app._estimate_runtime("minimax-mlx", 10), 33)

class DocumentationContract(unittest.TestCase):
    MINIMAX_PACKAGE_COMMIT = "b42e07bd2c0ffd14cc6b75ca19d9a96e5397eaf9"

    def test_readme_recreates_both_declared_environments(self):
        readme = (core.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("uv venv --python 3.12 .venv", readme)
        self.assertIn(
            "uv pip install --python .venv/bin/python -r requirements.txt",
            readme,
        )
        self.assertIn("uv venv --python 3.12 .venv-mlx", readme)
        self.assertIn(
            "uv pip install --python .venv-mlx/bin/python \\\n"
            "  \"mlx-minimax-music3 @ git+https://github.com/vanch007/"
            f"mlx-minimax-music3.git@{self.MINIMAX_PACKAGE_COMMIT}\"\n"
            "uv pip check --python .venv/bin/python\n"
            "uv pip check --python .venv-mlx/bin/python\n"
            "./.venv/bin/python -m synth.cli models",
            readme,
        )
        self.assertIn("uv pip check --python .venv/bin/python", readme)
        self.assertIn("uv pip check --python .venv-mlx/bin/python", readme)
        self.assertIn("./.venv/bin/python -m synth.cli models", readme)

        metadata_paths = list(
            (core.PROJECT_ROOT / ".venv-mlx").glob(
                "lib/python*/site-packages/"
                "mlx_minimax_music3-*.dist-info/direct_url.json"
            )
        )
        self.assertEqual(len(metadata_paths), 1, "installed MiniMax source metadata missing")
        direct_url = json.loads(metadata_paths[0].read_text(encoding="utf-8"))
        self.assertEqual(
            direct_url["vcs_info"]["commit_id"],
            self.MINIMAX_PACKAGE_COMMIT,
        )

    def test_minimax_conversion_is_documented_at_the_real_boundary(self):
        gotchas = (core.PROJECT_ROOT / "docs" / "gotchas.md").read_text(encoding="utf-8")
        self.assertIn("The runner returns JSON from `mlx_minimax_music3.cli`", gotchas)
        self.assertIn("package's `audio.py`", gotchas)
        self.assertNotIn("See `runners/minimax_mlx_runner.py`", gotchas)

        audio_paths = list(
            (core.PROJECT_ROOT / ".venv-mlx").glob(
                "lib/python*/site-packages/mlx_minimax_music3/audio.py"
            )
        )
        self.assertEqual(len(audio_paths), 1, "installed MiniMax audio source missing")
        audio_source = audio_paths[0].read_text(encoding="utf-8")
        for source_contract in (
            "np.asarray(audio[0].astype(mx.float32)).T",
            "np.isfinite(values).all()",
            "np.clip(values, -1.0, 1.0)",
            'format="WAV", subtype="PCM_16"',
        ):
            self.assertIn(source_contract, audio_source)

    def test_xet_workaround_claim_names_every_actual_location(self):
        marker = 'os.environ.setdefault("HF_HUB_DISABLE_XET", "1")'
        search_roots = (core.PROJECT_ROOT / "synth", core.PROJECT_ROOT / "runners")
        actual = {
            path.relative_to(core.PROJECT_ROOT).as_posix()
            for search_root in search_roots
            for path in search_root.rglob("*.py")
            if path != Path(__file__)
            if marker in path.read_text(encoding="utf-8")
        }
        expected = {
            "synth/core.py",
            "runners/minimax_mlx_runner.py",
            "runners/musicgen_runner.py",
        }
        self.assertEqual(actual, expected)
        gotchas = (core.PROJECT_ROOT / "docs" / "gotchas.md").read_text(encoding="utf-8")
        for location in expected:
            self.assertIn(f"`{location}`", gotchas)


if __name__ == "__main__":
    unittest.main()
