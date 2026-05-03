# AI Execution Engine

> LLM proposes. System disposes.

This runtime is used by higher-level agent systems:

- [Slyog/execution-trace-ui](https://github.com/Slyog/execution-trace-ui)
- [Slyog/adaptive-execution](https://github.com/Slyog/adaptive-execution)

---

## Overview

AI Execution Engine runs AI-generated Python code in an isolated Docker runtime and determines correctness through actual execution.

Each attempt is executed, observed, and recorded as a trace. Exit code, `stdout`, `stderr`, timeout state, and status define whether an attempt succeeded.

---

## System Overview

This repository is part of a 3-layer execution system:

| Layer | Role | Repo |
|---|---|---|
| **AI-Execution-Engine** *(this repo)* | Executes Python code in a deterministic Docker runtime | [Slyog/AI-Execution-Engine](https://github.com/Slyog/AI-Execution-Engine) |
| **adaptive-execution** | Interprets failures and applies repair strategies | [Slyog/adaptive-execution](https://github.com/Slyog/adaptive-execution) |
| **Tracewell Runtime** (UI) | Visualizes execution traces and decisions | [Slyog/execution-trace-ui](https://github.com/Slyog/execution-trace-ui) |

---

## What This Is

- Controlled runtime for AI-generated Python code
- Docker-based isolation
- Deterministic execution results
- Self-repair loop using real runtime feedback
- Persisted sessions, runs, and traces

## What This Is Not

- Not a chatbot
- Not a code-generation demo
- Not LLM-only verification

---

## Architecture

> The model proposes code. The system determines truth through execution.

**Raw execution path:**

```text
Client → /execute → DockerRunner
```

**Engine-native agent run:**

```text
Client → /agent-runs → AgentLayer → RunManager → DockerRunner → TraceManager
```

| Component | Role |
|---|---|
| `AgentLayer` | Generates candidate Python code |
| `RunManager` | Orchestrates execution attempts |
| `DockerRunner` | Executes code in an isolated container |
| `TraceManager` | Records every attempt and result |

---

## Example API Call

```bash
curl -X POST http://localhost:8000/agent-runs \
  -H "Content-Type: application/json" \
  -d '{"objective":"Write Python code that prints hello from runtime","max_attempts":3}'
```

**Response:**

```json
{
  "status": "completed",
  "attempts": 1,
  "final_stdout": "hello from runtime\n",
  "trace_ids": ["816ba0ca-7a32-4ebc-bcad-204237a5ebcb"]
}
```

**Full trace (real execution):**

```json
{
  "objective": "Write Python code that prints hello from runtime",
  "generated_code": "print(\"hello from runtime\")",
  "exit_code": 0,
  "stdout": "hello from runtime",
  "status": "completed",
  "trace_id": "816ba0ca-7a32-4ebc-bcad-204237a5ebcb"
}
```

> Correctness is determined by actual execution (`exit_code` + `stdout`), not by model output alone.

---

## Design Principles

> This system exists because LLM output is unreliable until it has been executed.

- Execution result is the source of truth
- Status is never decided by the model
- Failed runs are repaired from observed runtime output
- Retries are explicit and traceable
- Session state is deterministic and file-backed

---

## System Composition

The separation between layers is intentional. AI Execution Engine stays independent — higher-level systems use it, but this repository is not responsible for their behavior.

| Layer | Role |
|---|---|
| **AI Execution Engine** *(this repo)* | Runtime + truth layer. Executes Python code in Docker and returns `stdout`, `stderr`, `exit_code`. |
| **adaptive-execution** | Adaptive layer. Proposes code, observes failures, retries with failure context. |
| **Lightwell Runtime Agent** | Observation layer. Reads and logs runtime traces, providing history and inspection. |

**System flow:**

```text
# Adaptive layer
adaptive-execution → /execute → AI Execution Engine → DockerRunner

# Engine-native agent run
Client → /agent-runs → AgentLayer → RunManager → DockerRunner → TraceManager

# Observation layer
AI Execution Engine traces → Lightwell Runtime Agent
```

---

## How To Run (Local)

**Install dependencies:**

```bash
pip install -r requirements.txt
cp .env.example .env
```

**Set in `.env`:**

```env
OPENAI_API_KEY=your_key
SESSION_DATA_DIR=./data/sessions
```

**Start the engine:**

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

## Local Sandbox-To-Host API Test

For local API debugging, start `adaptive-execution` on port `8880`, then start AI Execution Engine on port `8000` and run:

```bash
python scripts/run_demo_users_sandbox.py
```

This posts `scripts/test_demo_users_local.py` to `/sandbox-runs` with `allow_network=true` — code is executed directly without LLM generation.

The script calls the local demo API through:

```text
http://host.docker.internal:8880/demo/users
```

**Expected status sequence:**

```text
401 → 400 → 200
```
