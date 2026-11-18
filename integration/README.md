# Generic Jusi managed-URL extension

`jusi-managed-urls.patch` records the generic core extension against the sibling
Jusi 1.0.6 checkout. The extension and its lifecycle correction have been applied
to `../jusi` with the user's approval. Do not apply either patch again there.

`jusi-managed-urls-fix.patch` updates that original extension to handle navigation
while both page and terminal are hidden, share placement across application and
worker-result opens, and retry failed page cleanup. For a checkout with the
original extension, apply only this incremental fix:

```sh
git apply --check ../jusi-web/integration/jusi-managed-urls-fix.patch
git apply ../jusi-web/integration/jusi-managed-urls-fix.patch
```

The full extension patch already includes this fix for clean installations.

The plugin needs these generic APIs to implement one replaceable page per cell:

```python
from jusi.editor_client import open_url, close_url
open_url("https://example.com", slot="page")
close_url(slot="page")
```

Slots belong to a verified Jusi client within its notebook session. Replacement
deletes the previous web buffer, including hidden buffers. Closing is idempotent
and cannot close the terminal client. Unkeyed opens retain their existing
independent lifetime. Closing a source client leaves its last page available.
Managed pages occupy the source plugin's window. Closing a slot restores its
terminal there, while windows reused for unrelated content are preserved.
If all projections are hidden, a managed open reveals the same source terminal
in a new window and replaces its previous page regardless of tab or visibility.
Native page/window close leaves the terminal available through `JusiToggleFocus`.

The patch includes Python/Lua/schema changes, shared fixtures, socket tests,
frontend lifecycle tests, architecture documentation and accepted ADR 0053.
It introduces no plugin-specific frontend logic or browser-host keybindings.

To apply it to a separate checkout at the same baseline, run from that checkout:

```sh
git apply --check ../jusi-web/integration/jusi-managed-urls.patch
git apply ../jusi-web/integration/jusi-managed-urls.patch
```

Then install Jusi and this plugin into the target environment. The Lua frontend
must also use the updated Jusi checkout.

The patch was tested in a temporary checkout and then in the actual sibling
checkout after application; see [validation results](VALIDATION.md).
The plugin's full service/kernel/VisiData/Neovim lifecycle test can be run against
any checkout containing the extension:

```sh
PYTHONPATH=/path/to/jusi/src JUSI_SOURCE_ROOT=/path/to/jusi python -m pytest
```

The test substitutes the WebBuffer host command and Perplexity HTTP endpoint;
it does not call the paid API or claim to test Electron rendering.
