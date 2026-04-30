import os
import re
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


PROMPT_VERSION = "v1"
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class AgentCodeResult:
    code: str
    prompt: str
    model: str
    prompt_version: str
    tokens_input: int | None
    tokens_output: int | None


class AgentLayer:
    def __init__(self, api_key: str | None = None):
        load_dotenv()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("missing_openai_api_key")
        self.client = OpenAI(api_key=self.api_key)

    def generate_code(self, objective: str, model: str = DEFAULT_MODEL) -> AgentCodeResult:
        prompt = self._generation_prompt(objective)
        return self._create_code_result(prompt=prompt, model=model)

    def repair_code(
        self,
        objective: str,
        previous_code: str,
        previous_error: dict[str, Any] | str,
        model: str = DEFAULT_MODEL,
    ) -> AgentCodeResult:
        prompt = self._repair_prompt(objective, previous_code, previous_error)
        return self._create_code_result(prompt=prompt, model=model)

    def _create_code_result(self, *, prompt: str, model: str) -> AgentCodeResult:
        response = self.client.responses.create(
            model=model,
            instructions=self._system_instructions(),
            input=prompt,
        )

        return AgentCodeResult(
            code=strip_markdown_fences(self._extract_output_text(response)),
            prompt=prompt,
            model=model,
            prompt_version=PROMPT_VERSION,
            tokens_input=self._usage_value(response, "input_tokens"),
            tokens_output=self._usage_value(response, "output_tokens"),
        )

    def _generation_prompt(self, objective: str) -> str:
        return "\n".join(
            [
                "Generate Python code for this request.",
                "",
                "Sandbox constraints:",
                "- Python only.",
                "- Standard library only.",
                "- No network access.",
                "- Do not install dependencies.",
                "- Do not assume filesystem access unless the request explicitly asks for it.",
                "- Print the final result to stdout.",
                "- Return executable Python code only.",
                "- Do not include markdown fences or explanations.",
                "",
                "Request:",
                objective,
            ]
        )

    def _repair_prompt(self, objective: str, previous_code: str, previous_error: dict[str, Any] | str) -> str:
        error = self._normalize_previous_error(previous_error)
        return "\n".join(
            [
                "Repair the previous Python code so it satisfies the original request.",
                "",
                "Original request:",
                objective,
                "",
                "Previous code:",
                previous_code,
                "",
                "Previous execution result:",
                f"status: {error['status']}",
                f"exit_code: {error['exit_code']}",
                f"stderr: {error['stderr']}",
                f"timed_out: {error['timed_out']}",
                "",
                "Sandbox constraints:",
                "- Python only.",
                "- Standard library only.",
                "- No network access.",
                "- Do not install dependencies.",
                "- Do not assume filesystem access unless the request explicitly asks for it.",
                "- Print the final result to stdout.",
                "- Return fixed executable Python code only.",
                "- Do not include markdown fences or explanations.",
            ]
        )

    def _normalize_previous_error(self, previous_error: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(previous_error, dict):
            return {
                "status": previous_error.get("status"),
                "exit_code": previous_error.get("exit_code"),
                "stderr": previous_error.get("stderr"),
                "timed_out": previous_error.get("timed_out"),
            }

        return {
            "status": "unknown",
            "exit_code": None,
            "stderr": str(previous_error),
            "timed_out": None,
        }

    def _system_instructions(self) -> str:
        return (
            "You generate candidate Python code for an isolated sandbox. "
            "Return only executable Python source code. Do not include markdown."
        )

    def _extract_output_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text is not None:
            return str(output_text)
        return str(response)

    def _usage_value(self, response: Any, name: str) -> int | None:
        usage = getattr(response, "usage", None)
        value = getattr(usage, name, None)
        return int(value) if value is not None else None


def generate_code(objective: str, model: str = DEFAULT_MODEL) -> AgentCodeResult:
    return AgentLayer().generate_code(objective, model=model)


def repair_code(
    objective: str,
    previous_code: str,
    previous_error: dict[str, Any] | str,
    model: str = DEFAULT_MODEL,
) -> AgentCodeResult:
    return AgentLayer().repair_code(objective, previous_code, previous_error, model=model)


def strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:python|py)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped
