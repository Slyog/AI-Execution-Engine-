import os
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, constr

from backend.agent_layer import AgentLayer
from backend.docker_runner import DockerRunner
from backend.run_manager import RunManager
from backend.session_manager import SessionManager
from backend.trace_manager import TraceManager


load_dotenv()
API_KEY = os.getenv("API_KEY")
SESSION_DATA_DIR = os.getenv("SESSION_DATA_DIR", "./data/sessions")

class CreateSessionRequest(BaseModel):
    """Request body for creating a persisted execution session."""

    label: constr(strip_whitespace=True, min_length=1)


class ExecuteRunRequest(BaseModel):
    """Request body containing Python code to execute."""

    code: constr(strip_whitespace=True, min_length=1)


class AgentRunRequest(BaseModel):
    """Request body for an agent-generated execution flow."""

    session_id: UUID | None = None
    objective: constr(strip_whitespace=True, min_length=1)
    max_attempts: int = Field(default=3, ge=1, le=5)
    model: constr(strip_whitespace=True, min_length=1) = "gpt-4o-mini"


class ExecuteResponse(BaseModel):
    """Stateless execution response used by tool clients."""

    status: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int


class SessionResponse(BaseModel):
    id: str = Field(description="Unique session identifier.")
    created_at: str = Field(description="UTC timestamp when the session was created.")
    label: str = Field(description="Human-readable session label.")


class RunResultResponse(BaseModel):
    stdout: str = Field(description="Captured standard output from the run.")
    stderr: str = Field(description="Captured standard error from the run.")
    exit_code: int = Field(description="Process exit code, or -1 for sandbox-level failures.")
    timed_out: bool = Field(description="Whether the run hit the configured timeout.")
    duration_ms: int = Field(description="Total execution duration in milliseconds.")


class RunResponse(BaseModel):
    id: str = Field(description="Unique run identifier.")
    created_at: str = Field(description="UTC timestamp when the run was created.")
    code: str = Field(description="Python source code that was executed.")
    status: str = Field(description="Run status: completed, execution_failed, timed_out, or internal_error.")
    result: RunResultResponse = Field(description="Normalized execution result.")


class TraceResponse(BaseModel):
    trace_id: str
    agent_run_id: str
    session_id: str
    run_id: str | None
    attempt: int
    objective: str
    model: str
    prompt_version: str
    prompt: str
    generated_code: str
    stdout: str
    stderr: str
    exit_code: int
    status: str
    duration_ms: int
    tokens_input: int | None
    tokens_output: int | None
    created_at: str


class AgentRunResponse(BaseModel):
    agent_run_id: str
    session_id: str
    status: str
    attempts: int
    final_code: str
    final_stdout: str
    final_stderr: str
    trace_ids: list[str]
    last_error: str | None = None


class ErrorResponse(BaseModel):
    detail: str = Field(description="Stable machine-readable error code.")


app = FastAPI(
    title="AI Execution Engine",
    description="API server for creating execution sessions and running isolated Python code.",
)

session_manager = SessionManager(SESSION_DATA_DIR)
run_manager = RunManager(session_manager, DockerRunner())
trace_manager = TraceManager(session_manager.base_path)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_api_key(request: Request):
    if API_KEY and request.headers.get("x-api-key") != API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


def ensure_agent_session(session_id: UUID | None, objective: str) -> str:
    if session_id is None:
        session = session_manager.create_session(f"agent: {objective[:80]}")
        return session["id"]

    session_id_str = str(session_id)
    session_manager.get_session(session_id_str)
    return session_id_str


def execution_error_from_run(run: dict) -> dict:
    result = run.get("result") if isinstance(run, dict) else {}
    result = result if isinstance(result, dict) else {}
    return {
        "status": run.get("status", "unknown") if isinstance(run, dict) else "unknown",
        "exit_code": result.get("exit_code"),
        "stderr": result.get("stderr", ""),
        "timed_out": result.get("timed_out", False),
    }


@app.exception_handler(RequestValidationError)
def handle_request_validation_error(request, exc):
    return JSONResponse(status_code=400, content={"detail": "invalid_input"})


@app.exception_handler(Exception)
def handle_unexpected_exception(request, exc):
    if isinstance(exc, FastAPIHTTPException):
        raise exc
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


@app.post(
    "/sessions",
    response_model=SessionResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create session",
    description="Create a persisted execution session that can hold one or more runs.",
)
def create_session(request: CreateSessionRequest):
    print("[POST] /sessions")

    try:
        session = session_manager.create_session(request.label)
        print(f"[POST] /sessions session_id={session['id']}")
        return session
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.get(
    "/sessions",
    response_model=list[SessionResponse],
    responses={500: {"model": ErrorResponse}},
    summary="List sessions",
    description="List persisted sessions in reverse creation order.",
)
def list_sessions():
    print("[GET] /sessions")

    try:
        return session_manager.list_sessions()
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get session",
    description="Fetch one persisted session by its UUID.",
)
def get_session(session_id: UUID):
    session_id_str = str(session_id)
    print(f"[GET] /sessions session_id={session_id_str}")

    try:
        return session_manager.get_session(session_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.get(
    "/sessions/{session_id}/traces",
    response_model=list[TraceResponse],
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List traces",
    description="List persisted execution traces for a session in reverse creation order.",
)
def list_traces(session_id: UUID):
    session_id_str = str(session_id)
    print(f"[GET] /sessions/{session_id_str}/traces session_id={session_id_str}")

    try:
        return trace_manager.list_traces_for_session(session_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.get(
    "/sessions/{session_id}/traces/{trace_id}",
    response_model=TraceResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get trace",
    description="Fetch one persisted execution trace by its UUID.",
)
def get_trace(session_id: UUID, trace_id: UUID):
    session_id_str = str(session_id)
    trace_id_str = str(trace_id)
    print(f"[GET] /sessions/{session_id_str}/traces/{trace_id_str} session_id={session_id_str}")

    try:
        return trace_manager.get_trace(session_id_str, trace_id_str)
    except FileNotFoundError as exc:
        detail = "trace_not_found" if exc.args and exc.args[0] == "trace_not_found" else "session_not_found"
        raise HTTPException(status_code=404, detail=detail)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.post(
    "/agent-runs",
    response_model=AgentRunResponse,
    response_model_exclude_none=True,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Execute agent run",
    description="Generate, execute, trace, and optionally repair Python code for a request.",
)
def execute_agent_run(request: AgentRunRequest):
    print("[POST] /agent-runs")

    try:
        session_id = ensure_agent_session(request.session_id, request.objective)
        agent = AgentLayer()
        agent_run_id = str(uuid4())
        trace_ids = []
        previous_code = ""
        previous_error = {}
        final_code = ""
        final_stdout = ""
        final_stderr = ""
        last_error = ""

        for attempt in range(1, request.max_attempts + 1):
            if attempt == 1:
                code_result = agent.generate_code(request.objective, model=request.model)
            else:
                code_result = agent.repair_code(
                    request.objective,
                    previous_code,
                    previous_error,
                    model=request.model,
                )

            run = run_manager.execute_run(session_id, code_result.code)
            status = run.get("status", "internal_error")
            result = run.get("result") if isinstance(run.get("result"), dict) else {}

            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = result.get("exit_code", -1)
            duration_ms = result.get("duration_ms", 0)

            trace = trace_manager.save_trace(
                session_id=session_id,
                agent_run_id=agent_run_id,
                run_id=run.get("id"),
                attempt=attempt,
                objective=request.objective,
                model=code_result.model,
                prompt_version=code_result.prompt_version,
                prompt=code_result.prompt,
                generated_code=code_result.code,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                status=status,
                duration_ms=duration_ms,
                tokens_input=code_result.tokens_input,
                tokens_output=code_result.tokens_output,
            )
            trace_ids.append(trace["trace_id"])

            final_code = code_result.code
            final_stdout = stdout
            final_stderr = stderr

            if status == "internal_error":
                raise HTTPException(status_code=500, detail="internal_error")

            if status == "completed":
                return {
                    "agent_run_id": agent_run_id,
                    "session_id": session_id,
                    "status": "completed",
                    "attempts": attempt,
                    "final_code": final_code,
                    "final_stdout": final_stdout,
                    "final_stderr": final_stderr,
                    "trace_ids": trace_ids,
                }

            previous_code = code_result.code
            previous_error = execution_error_from_run(run)
            last_error = stderr or status

        return {
            "agent_run_id": agent_run_id,
            "session_id": session_id,
            "status": "failed",
            "attempts": request.max_attempts,
            "final_code": final_code,
            "final_stdout": final_stdout,
            "final_stderr": final_stderr,
            "last_error": last_error,
            "trace_ids": trace_ids,
        }
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
    except RuntimeError as exc:
        if str(exc) == "missing_openai_api_key":
            raise HTTPException(status_code=500, detail="missing_openai_api_key")
        raise HTTPException(status_code=500, detail="internal_error")
    except ValueError as exc:
        if "session_not_found" in str(exc):
            raise HTTPException(status_code=404, detail="session_not_found")
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.post(
    "/sessions/{session_id}/runs",
    response_model=RunResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Execute run",
    description="Execute Python code inside the sandbox and persist the resulting run under the given session.",
)
def execute_run(session_id: UUID, request: ExecuteRunRequest):
    session_id_str = str(session_id)
    print(f"[POST] /sessions/{session_id_str}/runs session_id={session_id_str}")

    try:
        run = run_manager.execute_run(session_id_str, request.code)
        print(f"[POST] /sessions/{session_id_str}/runs session_id={session_id_str} run_id={run['id']}")

        status = run["status"]
        if status == "internal_error":
            raise HTTPException(status_code=500, detail="internal_error")

        return run
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.post(
    "/execute",
    response_model=ExecuteResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Execute code statelessly",
    description="Create an internal tool session, run the provided Python code, and return only the normalized result.",
)
def execute_tool(request: ExecuteRunRequest, http_request: Request):
    print("[POST] /execute")

    try:
        require_api_key(http_request)
        session = session_manager.create_session("tool")
        run = run_manager.execute_run(session["id"], request.code)

        result = run["result"]
        status = run["status"]

        return {
            "status": status,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "exit_code": result["exit_code"],
            "timed_out": result["timed_out"],
            "duration_ms": result["duration_ms"],
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")


@app.get(
    "/sessions/{session_id}/runs",
    response_model=list[RunResponse],
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List runs",
    description="List persisted runs for a session in reverse creation order.",
)
def list_runs(session_id: UUID):
    session_id_str = str(session_id)
    print(f"[GET] /sessions/{session_id_str}/runs session_id={session_id_str}")

    try:
        return session_manager.list_runs(session_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_input")
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")
