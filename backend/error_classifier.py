def status_from_result(result: dict) -> str:
    if result.get("timed_out"):
        return "timed_out"
    if str(result.get("stderr", "")).startswith("internal error:"):
        return "internal_error"
    if result.get("exit_code") != 0:
        return "execution_failed"
    return "completed"
