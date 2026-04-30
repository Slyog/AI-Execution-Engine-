# Architectural Decisions

## System Scope

AI Execution Engine provides an isolated runtime for generated Python code. It persists sessions, runs, and traces so every result can be inspected and replayed.

## Evaluated Approaches

### Container-Based Execution

Pros:

- Strong OS-level isolation
- Built-in resource limits
- Clear execution boundary
- Portable runtime behavior

Cons:

- Container startup latency
- Higher overhead than in-process execution

### In-Process Execution

Pros:

- Very fast startup
- Simple Python execution model

Cons:

- Weak isolation for untrusted code
- Limited process and filesystem control

### Host Process Sandboxing

Pros:

- Lightweight
- Flexible

Cons:

- Complex to secure correctly
- Requires manual resource enforcement
- High risk if isolation is incomplete

## Chosen Approach

Docker-based execution.

## Rationale

Docker provides the best balance of isolation, resource control, portability, and operational clarity for this engine.

## Execution Model

Code runs through Docker with Python isolated mode:

```text
docker run ... python -I -c "<code>"
```

Key decisions:

- No stdin, to avoid blocking runs
- No shell, to reduce attack surface
- Read-only root filesystem
- Explicit temporary writable mounts
- Network disabled by default

## Resource Isolation

Each run enforces:

- Memory limit
- CPU limit
- Process limit
- Dropped Linux capabilities
- No new privileges

## Persistence Strategy

Persistence is file-based:

```text
data/sessions/<session_id>/
```

Each session contains metadata, run history, execution results, and traces.

Benefits:

- Simple
- Deterministic
- Restart-safe
- No database required

## Timeout Design

Timeouts include both container startup and code execution. This avoids false timeout results on machines where container startup adds noticeable overhead.

## Future Improvements

- Warm container pool
- Queue-backed execution workers
- Per-session quotas
- Stronger isolation backends
- Richer trace search and replay

## Trade-Off Summary

| Aspect | Decision |
| --- | --- |
| Isolation | Docker |
| Persistence | File system |
| Execution | `python -I -c` |
| API | FastAPI |

## Conclusion

The design prioritizes safety, determinism, simplicity, and traceability while keeping the core execution loop small.
