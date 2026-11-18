import json
from pathlib import Path
import subprocess
import sys

import pytest

from jusi.plugin_api import validate_discovered_entry
from jusi.protocol import ProtocolValidationError, validate_plugin_kernel_message

from jusi_web import __version__
from jusi_web.catalog import catalog_entry
from jusi_web import kernel


def test_discovery_is_data_only_in_fresh_process():
    code = """
import json, sys
from importlib.metadata import entry_points
entry = next(e for e in entry_points(group='jusi.plugins.v1') if e.name == 'jusi_web')
catalog = entry.load()()
assert not any(name in sys.modules for name in ('visidata', 'IPython', 'jusi_web.worker', 'jusi_web.application'))
print(json.dumps(catalog))
"""
    # pythonpath in pytest is not inherited by Python; use the installed project.
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    catalog = json.loads(result.stdout)
    validate_discovered_entry(catalog, entry_point_name="jusi_web", distribution="jusi-web", distribution_version=__version__)
    with pytest.raises(ProtocolValidationError):
        validate_discovered_entry(catalog, entry_point_name="jusi_web", distribution="jusi-web", distribution_version="999")


def test_kernel_handoff_and_bootstrap(monkeypatch):
    from IPython import display

    records = []
    monkeypatch.setattr(display, "display", lambda value, **kwargs: records.append(value))

    class IPython:
        def register_magic_function(self, function, **kwargs):
            self.magic = function

    shell = IPython()
    kernel.configure_jusi_runtime_v1({"web": {"api_key_env": "MY_KEY"}})
    kernel.load_ipython_extension(shell)
    shell.magic("", "https://example.test")
    record = records[-1][kernel.HANDOFF_MIME]
    validate_plugin_kernel_message(record)
    assert record["payload"] == {"body": "https://example.test", "config": {"api_key_env": "MY_KEY"}}
    shell.magic.__jusi_bootstrap_v1__("")
    assert records[-1][kernel.HANDOFF_MIME]["payload"]["body"] == ""
    assert catalog_entry()["families"][0]["capabilities"] == ["execute", "bootstrap", "followup", "editor_actions"]
