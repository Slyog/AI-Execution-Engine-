# AI Execution Engine

LLM proposes. System disposes.

AI Execution Engine runs AI-generated Python code in an isolated Docker runtime and records each attempt as an inspectable trace. Exit code, stdout, stderr, timeout state, and status determine whether an attempt succeeded.

## What This Is

- Controlled runtime for AI-generated Python code
- Docker-based isolation
- Deterministic execution results
- Self-repair loop using real runtime feedback
- Persisted sessions, runs, and traces

## What This Is Not

- A chatbot
- A code-generation demo
- LLM-only verification

## Architecture

The model proposes code; the engine determines truth through execution.

```text
Client → /agent-runs → AgentLayer → RunManager → DockerRunner → TraceManager
```

`AgentLayer` generates candidate Python code. `RunManager` sends it to `DockerRunner`. `DockerRunner` executes it in an isolated container. `TraceManager` stores each attempt and result.

## Example API Call

```bash
curl -X POST http://localhost:8000/agent-runs \
  -H "Content-Type: application/json" \
  -d '{"objective":"Write Python code that prints hello from runtime","max_attempts":3}'
```

## Example Response

```json
{
  "status": "completed",
  "attempts": 1,
  "final_stdout": "hello from runtime\n",
  "trace_ids": ["816ba0ca-7a32-4ebc-bcad-204237a5ebcb"]
}
```

## Example Run (Real Execution)

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

The trace shows that correctness is determined by actual execution (exit code and stdout), not by model output alone.

## Design Principles

This system exists because LLM output is unreliable until it has been executed.

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

## Used By

This runtime is used by an external agent workspace:

https://github.com/Slyog/lightwell-runtime-agent

Lightwell is a separate layer that:

- sends objectives to `/agent-runs`
- observes execution results
- logs and classifies failures
- provides a UI layer

Execution Engine = runtime + truth layer
Lightwell = interface + observation layer
