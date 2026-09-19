# Security and operational safety

This is a local single-user tool, not an internet service or a secure multi-tenant
host. Do not port-forward it, publish its launcher token, or run it elevated.

The HTTP listener is fixed to 127.0.0.1; Host and Origin are checked. Every API
request requires a per-process bearer token. No wildcard CORS is enabled. CSP,
no-store, no-referrer, nosniff and frame protections are sent. The browser receives
the token in its URL fragment, moves it to session storage, then removes the
fragment. It is not placed in query strings or request logs. The MCP relay reads a
local descriptor; on Unix that descriptor is chmod 600. On Windows it inherits
normal user-workspace ACLs. Same-user malware/admin access is outside the boundary.

Only explicit imports and generated exports can be retrieved by opaque asset ID.
There is no HTTP arbitrary path, shell, Python execution, network audio downloader,
FFmpeg filter-expression input, driver installation, or unrestricted FL command
endpoint. Uploaded codecs still use native libraries; this build does not sandbox
a malicious codec exploit. Keep dependencies current through reviewed releases
and do not process untrusted files while sensitive work is open.

No inference request is sent unless a loopback endpoint is explicitly configured.
Project names and plugin names are untrusted data, not instructions. Validation
and locks remain outside the model. An MCP client is expected to honor explicit
user authorization; the relay cannot itself prove a human clicked in that client.
For strongest oversight, use the desktop preview and approval button.

All mutation paths are serialized. The Stop latch blocks future actions but cannot
cancel or undo a command already accepted by FL. Rendering cancellation terminates
only the owned child; no process-name-based global kill is used. The optional
Windows stop hotkey records no keystrokes and injects none; it merely registers
one key combination and reports whether registration succeeded.

Do not run other PostFader writers alongside this app. Do not manually move the
same FL controls while a plan runs. The live bridge is not a cryptographically
authenticated remote authority: endpoint selection and local trust still matter.
The app's lock cannot stop another independently installed client using a different
workspace or communicating with FL outside this process. Upstream MIDI ownership
and write-mode checks add protection, not absolute OS-wide exclusivity.

A numeric readback is not proof that a plugin sounds correct. FL may quantize
parameters, defer updates, or expose display values differently. Unknown outcomes
are intentionally inconvenient: inspect and acknowledge them rather than retrying.

Save a new project version manually before testing. The optional checkpoint is
only a copy of already-saved bytes and does not include unsaved edits or samples.
No automated save, complete state rollback, or guaranteed Undo is promised.


Diagnostic exports omit raw exceptions, local paths, device/endpoint names, project
contents, session fingerprints and authentication tokens. Those values can still
appear in the **local-only details** panel. Review any report before sharing.
Restore previews neither bypass the write block nor inherit old approval: they
are new plans, with current locks and a new digest, requiring fresh authorization.
