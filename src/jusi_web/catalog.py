"""Discovery is JSON-only and never imports the application or Jusi."""
from . import __version__


def catalog_entry():
    return {
        "plugin_id": "jusi_web",
        "plugin_version": __version__,
        "distribution": "jusi-web",
        "families": [{
            "family_id": "web", "magic_name": "web",
            "capabilities": ["execute", "bootstrap", "followup", "editor_actions"],
            "presentation": {"syntax": "", "indent": ""},
        }],
        "kernel_extensions": ["jusi_web.kernel"],
        "worker_entry_point": "jusi_web.worker:create_worker",
        "media_types": ["text/x-ansi"],
        "interaction": "terminal_interactive",
    }
