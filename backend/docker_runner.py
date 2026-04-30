import subprocess
import time


MAX_OUTPUT_BYTES = 1_000_000


class DockerRunner:
    def __init__(
        self,
        image: str = "python:3.11-alpine",
        timeout_seconds: int = 10,
        memory_limit: str = "128m",
        cpu_quota: float = 0.5,
        network_disabled: bool = True,
    ):
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota
        self.network_disabled = network_disabled

    def run_python(self, code: str) -> dict:
        started_at = time.monotonic()
        process = None

        try:
            stdout, stderr, timed_out, exit_code, process = self._run_and_capture(code)
            if timed_out:
                return self._result(
                    stdout="",
                    stderr="execution timed out",
                    exit_code=-1,
                    timed_out=True,
                    started_at=started_at,
                )

            return self._result(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=timed_out,
                started_at=started_at,
            )
        except subprocess.TimeoutExpired:
            return self._result(
                stdout="",
                stderr="execution timed out",
                exit_code=-1,
                timed_out=True,
                started_at=started_at,
            )
        except Exception as exc:
            return self._result(
                stdout="",
                stderr=f"execution_failed: {exc}",
                exit_code=-1,
                timed_out=False,
                started_at=started_at,
            )
        finally:
            self._cleanup_process(process)

    def _run_and_capture(self, code: str) -> tuple[str, str, bool, int, subprocess.Popen]:
        command = [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--workdir",
            "/workspace",
            "--user",
            "65534:65534",
            "--memory",
            self.memory_limit,
            "--cpus",
            self._format_cpus(self.cpu_quota),
            "--pids-limit",
            "64",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs",
            "/workspace:rw,noexec,nosuid,size=16m",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONUNBUFFERED=1",
        ]

        if self.network_disabled:
            command.extend(["--network", "none"])

        command.extend([self.image, "python", "-I", "-c", code])

        print("[DockerRunner] starting docker run")
        print(f"[DockerRunner] code={code}")
        print(f"[DockerRunner] cmd={' '.join(command)}")
        start_time = time.monotonic()

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print("[DockerRunner] process started")

        try:
            raw_stdout, raw_stderr = process.communicate(timeout=self.timeout_seconds)
            print("[DockerRunner] communicate returned")
            end_time = time.monotonic()
            print(f"[DockerRunner] duration={end_time - start_time:.2f}s")
            print(f"[DockerRunner] returncode={process.returncode}")
            print(f"[DockerRunner] raw stdout bytes={len(raw_stdout)}")
            print(f"[DockerRunner] raw stderr bytes={len(raw_stderr)}")
            return (
                self._decode_output(raw_stdout),
                self._decode_output(raw_stderr),
                False,
                process.returncode if process.returncode is not None else 1,
                process,
            )
        except subprocess.TimeoutExpired:
            print("[DockerRunner] TIMEOUT EXPIRED")
            try:
                process.kill()
            except Exception:
                pass

            try:
                raw_stdout, raw_stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                raw_stdout = b""
                raw_stderr = b""

            end_time = time.monotonic()
            print(f"[DockerRunner] duration={end_time - start_time:.2f}s")
            print(f"[DockerRunner] returncode={process.returncode}")
            print(f"[DockerRunner] raw stdout bytes={len(raw_stdout)}")
            print(f"[DockerRunner] raw stderr bytes={len(raw_stderr)}")
            return (
                self._decode_output(raw_stdout),
                self._decode_output(raw_stderr),
                True,
                -1,
                process,
            )

    def _cleanup_process(self, process: subprocess.Popen | None) -> None:
        if process is None:
            return

        try:
            if process.poll() is None:
                process.kill()
        except Exception:
            pass

        try:
            process.communicate(timeout=1)
        except Exception:
            pass

    def _decode_output(self, data: bytes) -> str:
        if len(data) > MAX_OUTPUT_BYTES:
            data = data[:MAX_OUTPUT_BYTES]
        return data.decode("utf-8", errors="replace")

    def _result(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        timed_out: bool,
        started_at: float,
    ) -> dict:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        print(f"[DockerRunner] completed in {duration_ms}ms")
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
        }

    def _format_cpus(self, value: float) -> str:
        # Docker --cpus is a best-effort scheduler limit, not a hard realtime cap.
        return f"{max(value, 0.01):.2f}"
