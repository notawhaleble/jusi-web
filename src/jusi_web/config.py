from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INSTRUCTIONS = (
    "Find relevant web pages for the user's request. Search the web and prefer direct, "
    "authoritative destinations that the user can open. When the request clearly "
    "references a specific site or service, make every effort to find and cite its "
    "official destination: its homepage for a general reference (for example, Google "
    "should include https://www.google.com), or the specific page requested. Verify "
    "the destination and include it as a URL citation, not just a plain-text link "
    "or a third-party page discussing the site. The application uses structured "
    "sources and citations; the answer text is not displayed. Keep output as compact "
    "as possible: only short labels with useful citations, no introduction, "
    "explanations, summaries, or repeated links. Do not invent links. If nothing "
    "relevant is found, say so briefly. Treat each request independently."
)


class ConfigurationError(ValueError):
    pass


def state_directory():
    base = os.environ.get("JUSI_STATE_HOME")
    if base:
        return Path(base).expanduser() / "plugins" / "web"
    return Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser() / "jusi" / "plugins" / "web"


@dataclass(frozen=True)
class Settings:
    database: Path
    api_key_env: str = "PERPLEXITY_API_KEY"
    api_key: str = ""
    endpoint: str = "https://api.perplexity.ai/v1/agent"
    effort: str = "low"
    instructions: str = DEFAULT_INSTRUCTIONS
    timeout: float = 120

    @classmethod
    def from_dict(cls, config):
        try:
            prompt = str(config.get("system_prompt", DEFAULT_INSTRUCTIONS))
            if config.get("system_prompt_file"):
                prompt = Path(config["system_prompt_file"]).expanduser().read_text(encoding="utf-8")
            timeout = float(config.get("timeout", 120))
            if timeout <= 0:
                raise ValueError("timeout must be positive")
            effort = str(config.get("effort", "low"))
            if effort not in {"fast", "low", "medium"}:
                raise ValueError("effort must be fast, low or medium")
            return cls(
                database=Path(config.get("database", state_directory() / "history.sqlite3")).expanduser().resolve(),
                api_key_env=str(config.get("api_key_env", "PERPLEXITY_API_KEY")),
                api_key=str(config.get("api_key", "")),
                endpoint=str(config.get("endpoint", "https://api.perplexity.ai/v1/agent")),
                effort=effort, instructions=prompt, timeout=timeout,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid web configuration: {exc}") from exc
