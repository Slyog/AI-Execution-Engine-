from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from backend.error_classifier import status_from_result


class RunManager:
    def __init__(self, session_manager, docker_runner):
        self.session_manager = session_manager
        self.docker_runner = docker_runner

    def execute_run(self, session_id: str, code: str) -> dict:
        self._validate_session(session_id)

        run = self._build_pending_run(code)
        persisted_run = self._persist_pending_run(session_id, run)
        run_id = persisted_run["id"]
        print(f"[RunManager] run={run_id} status=pending")

        try:
            result = self._execute_code(code)
        except Exception as exc:
            print("UNCAUGHT ERROR:", repr(exc))
            result = {
                "stdout": "",
                "stderr": f"internal error: {str(exc)}",
                "exit_code": -1,
                "timed_out": False,
                "duration_ms": 0,
            }

        final_status = self._final_status_from_result(result)
        result["status"] = final_status

        try:
            final_run = self._persist_result(session_id, persisted_run, result)
            normalized_run = self._normalize_run(final_run, fallback_run=persisted_run)
            print(f"[RunManager] run={run_id} status={final_status}")
            return normalized_run
        except Exception as exc:
            print(f"[RunManager] run={run_id} status=internal_error")
            fallback_run = dict(persisted_run)
            fallback_run["result"] = self._build_failed_result("internal_error", str(exc))
            fallback_run["status"] = "internal_error"

            try:
                fallback_run["result"]["status"] = fallback_run["status"]
                recovered_run = self._persist_result(session_id, persisted_run, fallback_run["result"])
                return self._normalize_run(recovered_run, fallback_run=fallback_run)
            except Exception:
                # TODO: SessionManager currently exposes no recovery API beyond
                # create_run/update_run. If the update path stays broken, the
                # pending run remains persisted but cannot be repaired here.
                return self._normalize_run(fallback_run, fallback_run=persisted_run)

    def _build_pending_run(self, code: str) -> dict:
        return {
            "id": str(uuid4()),
            "created_at": self._created_at(),
            "code": self._coerce_string(code),
            "status": "pending",
            "result": None,
        }

    def _validate_session(self, session_id: str) -> dict:
        try:
            return self.session_manager.get_session(session_id)
        except FileNotFoundError as exc:
            raise ValueError(f"session_not_found: {session_id}") from exc

    def _execute_code(self, code: str) -> dict:
        started_at = monotonic()

        try:
            raw_result = self.docker_runner.run_python(code)
        except Exception as exc:
            print("UNCAUGHT ERROR:", repr(exc))
            return {
                "stdout": "",
                "stderr": f"internal error: {str(exc)}",
                "exit_code": -1,
                "timed_out": False,
                "duration_ms": int((monotonic() - started_at) * 1000),
            }

        return self._normalize_execution_result(raw_result, started_at)

    def _persist_pending_run(self, session_id: str, run: dict) -> dict:
        created_run = self.session_manager.create_run(session_id, run["code"])
        if not isinstance(created_run, dict):
            raise RuntimeError("session_manager_create_run_returned_non_dict")
        if not self._has_non_empty_string(created_run.get("run_id")):
            raise RuntimeError("missing_run_id_from_session_manager")

        normalized_created_run = self._normalize_run(
            {
                "id": created_run.get("run_id"),
                "created_at": self._coerce_string(created_run.get("created_at"), fallback=run["created_at"]),
                "code": self._coerce_string(created_run.get("code"), fallback=run["code"]),
                "status": self._coerce_string(created_run.get("status"), fallback=run["status"]),
                "result": None,
            },
            fallback_run=run,
        )
        return normalized_created_run

    def _persist_result(self, session_id: str, run: dict, result: dict) -> dict:
        normalized_result = self._normalize_result(result)
        normalized_result["status"] = self._coerce_string(result.get("status"), fallback=run["status"])
        updated_run = self.session_manager.update_run(session_id, run["id"], normalized_result)
        if not isinstance(updated_run, dict):
            raise RuntimeError("session_manager_update_run_returned_non_dict")
        if not self._has_non_empty_string(updated_run.get("run_id")):
            raise RuntimeError("missing_run_id_from_session_manager")

        return {
            "id": updated_run.get("run_id"),
            "created_at": self._coerce_string(updated_run.get("created_at"), fallback=run["created_at"]),
            "code": self._coerce_string(updated_run.get("code"), fallback=run["code"]),
            "status": self._coerce_string(updated_run.get("status"), fallback=normalized_result["status"]),
            "result": {
                "stdout": updated_run.get("stdout"),
                "stderr": updated_run.get("stderr"),
                "exit_code": updated_run.get("exit_code"),
                "timed_out": normalized_result["timed_out"],
                "duration_ms": normalized_result["duration_ms"],
            },
        }

    def _normalize_execution_result(self, raw_result, started_at: float) -> dict:
        if not isinstance(raw_result, dict):
            return {
                "stdout": "",
                "stderr": "internal error: docker_runner_returned_non_dict",
                "exit_code": -1,
                "timed_out": False,
                "duration_ms": int((monotonic() - started_at) * 1000),
            }

        result = self._normalize_result(raw_result)

        if raw_result.get("duration_ms") is None:
            elapsed_ms = int((monotonic() - started_at) * 1000)
            result["duration_ms"] = max(elapsed_ms, 0)

        return result

    def _normalize_run(self, run, fallback_run: dict | None = None) -> dict:
        run_dict = run if isinstance(run, dict) else {}
        fallback = fallback_run if isinstance(fallback_run, dict) else {}
        raw_result = run_dict.get("result")
        normalized_result = self._normalize_result(raw_result or {})

        return {
            "id": self._require_id(run_dict.get("id")),
            "created_at": self._coerce_string(
                run_dict.get("created_at"),
                fallback=self._coerce_string(fallback.get("created_at"), fallback=self._created_at()),
            ),
            "code": self._coerce_string(run_dict.get("code"), fallback=self._coerce_string(fallback.get("code"))),
            "status": self._coerce_string(run_dict.get("status"), fallback=self._coerce_string(fallback.get("status"))),
            "result": normalized_result,
        }

    def _normalize_result(self, result) -> dict:
        result_dict = result if isinstance(result, dict) else {}
        return {
            "stdout": self._coerce_string(result_dict.get("stdout")),
            "stderr": self._coerce_string(result_dict.get("stderr")),
            "exit_code": self._coerce_int(result_dict.get("exit_code"), default=-1),
            "timed_out": bool(result_dict.get("timed_out", False)),
            "duration_ms": max(self._coerce_int(result_dict.get("duration_ms"), default=0), 0),
        }

    def _build_failed_result(self, error_kind: str, error_message: str) -> dict:
        message = self._coerce_string(error_message, fallback="unknown error").strip() or "unknown error"
        return {
            "stdout": "",
            "stderr": f"{error_kind}: {message}",
            "exit_code": -1,
            "timed_out": False,
            "duration_ms": 0,
        }

    def _coerce_string(self, value, fallback: str = "") -> str:
        if value is None:
            return fallback
        if isinstance(value, str):
            return value
        return str(value)

    def _coerce_int(self, value, default: int) -> int:
        if value is None or isinstance(value, bool):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _require_id(self, value) -> str:
        if self._has_non_empty_string(value):
            return value.strip()
        raise RuntimeError("missing_run_id")

    def _has_non_empty_string(self, value) -> bool:
        return isinstance(value, str) and value.strip() != ""

    def _final_status_from_result(self, result: dict) -> str:
        return status_from_result(self._normalize_result(result))

    def _created_at(self) -> str:
        return datetime.now(timezone.utc).isoformat()
