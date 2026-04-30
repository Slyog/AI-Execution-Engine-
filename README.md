# AI Execution Engine

LLM proposes. System disposes.

AI Execution Engine generates Python code, executes it in an isolated Docker runtime, and records each attempt as an inspectable trace. Runtime output is the source of truth: exit code, stdout, stderr, timeout state, and status determine whether an attempt succeeded.

## What This Is

- Controlled runtime for AI-generated Python code
- Docker-based isolation
- Deterministic execution results
- Self-repair loop using real runtime feedback
- Persisted sessions, runs, and traces

## What This Is Not

- Chatbot behavior
- Code-generation demo behavior
- LLM-only verification

## Architecture

The model proposes code; the engine determines truth through execution.

```text
Client -> /agent-runs -> AgentLayer -> RunManager -> DockerRunner -> TraceManager
```

`AgentLayer` generates candidate Python code. `RunManager` sends it to `DockerRunner`. `DockerRunner` executes it in an isolated container. `TraceManager` stores each attempt and result.

## Example API Call

```bash
curl -X POST http://localhost:8000/agent-runs \
  -H "Content-Type: application/json" \
  -d '{"objective":"Write Python code that prints hello from the engine","max_attempts":3}'
```

## Example Response

```json
{"status":"completed","attempts":1,"final_stdout":"hello from the engine\n","trace_ids":["841c0fae-b854-431e-a48f-7b502da7aaf3"]}
```

## Design Principles

- Execution result is the source of truth.
- Status is never decided by the model.
- Failed runs are repaired from observed runtime output.
- Retries are explicit and traceable.
- Session state is deterministic and file-backed.

## Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env
# set OPENAI_API_KEY=your_key and SESSION_DATA_DIR=./data/sessions in .env
uvicorn api:app --host 0.0.0.0 --port 8000
```
