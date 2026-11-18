from __future__ import annotations

from copy import deepcopy
from IPython.core.error import UsageError

from . import __version__

HANDOFF_MIME = "application/vnd.jusi.handoff.v1+json"
_configuration = {}


def configure_jusi_runtime_v1(configuration):
    global _configuration
    _configuration = deepcopy(configuration)


def jusi_kernel_adapter_v1():
    return {"plugin_id": "jusi_web", "plugin_version": __version__,
            "families": [{"family_id": "web", "magic_name": "web"}]}


def load_ipython_extension(ipython):
    def web(line, cell):
        from IPython.display import display

        if line.strip():
            raise UsageError("%%web takes no header arguments; put a URL, bookmark name or search in its body")
        config = _configuration.get("web", {})
        if not isinstance(config, dict):
            raise UsageError("[web] configuration must be a table")
        display({HANDOFF_MIME: {
            "protocol_version": 1, "kind": "plugin.handoff",
            "plugin_id": "jusi_web", "plugin_version": __version__,
            "family_id": "web", "magic_name": "web",
            "payload": {"body": cell, "config": deepcopy(config)},
        }}, raw=True)

    web.__jusi_bootstrap_v1__ = lambda line: web(line, "")
    ipython.register_magic_function(web, magic_kind="cell", magic_name="web")
