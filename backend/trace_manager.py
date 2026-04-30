import json
import os
import uuid
from datetime import datetime


class TraceManager:
    def __init__(self, base_path: str = "./data/sessions"):
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)

    def save_trace(
        self,
        *,
        session_id: str,
        agent_run_id: str,
        attempt: int,
        objective: str,
        model: str,
        prompt_version: str,
        prompt: str,
        generated_code: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        status: str,
        duration_ms: int,
        run_id: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
    ) -> dict:
        traces_dir = self._traces_dir(session_id)
        trace_id = str(uuid.uuid4())
        valid_session_id = self._validate_uuid(session_id, "session_not_found")
        valid_agent_run_id = self._validate_uuid(agent_run_id, "invalid_agent_run_id")
        valid_run_id = self._validate_uuid(run_id, "invalid_run_id") if run_id else None

        trace = {
            "trace_id": trace_id,
            "agent_run_id": valid_agent_run_id,
            "session_id": valid_session_id,
            "run_id": valid_run_id,
            "attempt": int(attempt),
            "objective": objective,
            "model": model,
            "prompt_version": prompt_version,
            "prompt": prompt,
            "generated_code": generated_code,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": int(exit_code),
            "status": status,
            "duration_ms": int(duration_ms),
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "created_at": datetime.utcnow().isoformat(),
        }

        self._write_json(os.path.join(traces_dir, f"{trace_id}.json"), trace)
        return trace

    def get_trace(self, session_id: str, trace_id: str) -> dict:
        return self._read_json(self._trace_file(session_id, trace_id))

    def list_traces_for_session(self, session_id: str) -> list[dict]:
        traces_dir = self._traces_dir(session_id)
        traces = []

        for entry in os.scandir(traces_dir):
            if not entry.is_file() or not entry.name.endswith(".json"):
                continue

            try:
                traces.append(self._read_json(entry.path))
            except Exception:
                continue

        traces.sort(key=lambda trace: trace["created_at"], reverse=True)
        return traces

    def _validate_uuid(self, value: str, error_name: str) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(error_name) from exc

    def _session_dir(self, session_id: str) -> str:
        valid_session_id = self._validate_uuid(session_id, "session_not_found")
        return os.path.join(self.base_path, valid_session_id)

    def _session_file(self, session_id: str) -> str:
        session_file = os.path.join(self._session_dir(session_id), "session.json")
        if not os.path.isfile(session_file):
            raise FileNotFoundError("session_not_found")
        return session_file

    def _traces_dir(self, session_id: str) -> str:
        self._session_file(session_id)
        traces_dir = os.path.join(self._session_dir(session_id), "traces")
        os.makedirs(traces_dir, exist_ok=True)
        return traces_dir

    def _trace_file(self, session_id: str, trace_id: str) -> str:
        valid_trace_id = self._validate_uuid(trace_id, "trace_not_found")
        trace_file = os.path.join(self._traces_dir(session_id), f"{valid_trace_id}.json")
        if not os.path.isfile(trace_file):
            raise FileNotFoundError("trace_not_found")
        return trace_file

    def _read_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def _write_json(self, path: str, data: dict) -> None:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
