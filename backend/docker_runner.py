import os
import subprocess
import sys
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
        self.docker_host, self.docker_host_source = self._select_docker_host()
        print(
            f"[DockerRunner] docker_host={self.docker_host or 'docker-cli-default'} "
            f"source={self.docker_host_source} platform={sys.platform}",
            flush=True,
        )

    def run_python(self, code: str, allow_network: bool = False) -> dict:
        started_at = time.monotonic()
        process = None

        try:
            stdout, stderr, timed_out, exit_code, process = self._run_and_capture(
                code,
                allow_network=allow_network,
            )
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

    def _run_and_capture(
        self,
        code: str,
        allow_network: bool = False,
    ) -> tuple[str, str, bool, int, subprocess.Popen]:
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

        network_disabled = self.network_disabled and not allow_network
        if network_disabled:
            command.extend(["--network", "none"])
        else:
            command.extend(["--add-host", "host.docker.internal:host-gateway"])

        command.extend([self.image, "python", "-I", "-c", code])
        add_host_gateway_enabled = self._command_has_host_gateway(command)

        print("[DockerRunner] starting docker run")
        print(f"[DockerRunner] network={'none' if network_disabled else 'enabled'}")
        print(f"[DockerRunner] code={code}")
        print(
            "[DockerRunner] host_gateway_mapping="
            f"{str(add_host_gateway_enabled).lower()} platform={sys.platform}",
            flush=True,
        )
        print(f"[DockerRunner] cmd={' '.join(command)}", flush=True)
        start_time = time.monotonic()

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._docker_environment(),
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

    def _select_docker_host(self) -> tuple[str | None, str]:
        configured_host = os.getenv("DOCKER_HOST", "").strip()
        if configured_host:
            if configured_host.lower().startswith("npipe:") and sys.platform != "win32":
                return "unix:///var/run/docker.sock", "linux-default-ignored-npipe-docker-host"
            return configured_host, "DOCKER_HOST"
        if sys.platform == "win32":
            return None, "docker-cli-default"
        return "unix:///var/run/docker.sock", "linux-default"

    def _docker_environment(self) -> dict:
        env = os.environ.copy()
        if self.docker_host:
            env["DOCKER_HOST"] = self.docker_host
        elif "DOCKER_HOST" not in os.environ:
            env.pop("DOCKER_HOST", None)
        return env

    def _command_has_host_gateway(self, command: list[str]) -> bool:
        return "--add-host" in command and "host.docker.internal:host-gateway" in command

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
