import json
import os
import uuid
from datetime import datetime


class SessionManager:
    def __init__(self, base_path: str = "./data/sessions"):
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)

    def create_session(self, label: str) -> dict:
        session_id = str(uuid.uuid4())
        session_dir = self._session_dir_from_valid_id(session_id)
        runs_dir = os.path.join(session_dir, "runs")

        os.makedirs(runs_dir, exist_ok=True)

        session = {
            "id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "label": label,
        }
        self._write_json(os.path.join(session_dir, "session.json"), session)
        return session

    def get_session(self, session_id: str) -> dict:
        session_file = self._session_file(session_id)
        return self._read_json(session_file)

    def list_sessions(self) -> list[dict]:
        sessions = []

        for entry in os.scandir(self.base_path):
            if not entry.is_dir():
                continue

            session_file = os.path.join(entry.path, "session.json")
            if not os.path.isfile(session_file):
                continue

            try:
                sessions.append(self._read_json(session_file))
            except Exception:
                continue

        sessions.sort(key=lambda session: session["created_at"], reverse=True)
        return sessions

    def create_run(self, session_id: str, code: str) -> dict:
        runs_dir = self._runs_dir(session_id)
        run_id = str(uuid.uuid4())
        run = {
            "run_id": run_id,
            "code": code,
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        self._write_json(os.path.join(runs_dir, f"{run_id}.json"), run)
        return run

    def update_run(self, session_id: str, run_id: str, result: dict) -> dict:
        run_file = self._run_file(session_id, run_id)
        run = self._read_json(run_file)

        run["stdout"] = result.get("stdout", "")
        run["stderr"] = result.get("stderr", "")
        run["exit_code"] = result.get("exit_code")
        if "status" in result:
            run["status"] = result["status"]

        self._write_json(run_file, run)
        return run

    def list_runs(self, session_id: str) -> list[dict]:
        runs_dir = self._runs_dir(session_id)
        runs = []

        for entry in os.scandir(runs_dir):
            if not entry.is_file() or not entry.name.endswith(".json"):
                continue

            try:
                runs.append(self._read_json(entry.path))
            except Exception:
                continue

        runs.sort(key=lambda run: run["created_at"], reverse=True)
        return runs

    def _validate_uuid(self, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError) as exc:
            raise FileNotFoundError(value) from exc

    def _session_dir(self, session_id: str) -> str:
        valid_session_id = self._validate_uuid(session_id)
        return self._session_dir_from_valid_id(valid_session_id)

    def _session_dir_from_valid_id(self, session_id: str) -> str:
        return os.path.join(self.base_path, session_id)

    def _session_file(self, session_id: str) -> str:
        session_dir = self._session_dir(session_id)
        session_file = os.path.join(session_dir, "session.json")
        if not os.path.isfile(session_file):
            raise FileNotFoundError(session_id)
        return session_file

    def _runs_dir(self, session_id: str) -> str:
        self._session_file(session_id)
        session_dir = self._session_dir(session_id)
        runs_dir = os.path.join(session_dir, "runs")
        os.makedirs(runs_dir, exist_ok=True)
        return runs_dir

    def _run_file(self, session_id: str, run_id: str) -> str:
        valid_run_id = self._validate_uuid(run_id)
        run_file = os.path.join(self._runs_dir(session_id), f"{valid_run_id}.json")
        if not os.path.isfile(run_file):
            raise FileNotFoundError(run_id)
        return run_file

    def _read_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def _write_json(self, path: str, data: dict) -> None:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
