# Third-party provenance and redistribution boundary

The application-specific Python, web UI, tests and documentation are provided under
the MIT license in LICENSE. No claim is made over the external foundations below.

## PostFader

- Repository: https://github.com/synopsys0/postfader-fl-studio-mcp
- Source revision reviewed: `480bedd1cde98fe272c5e02f66efd7aa83315d0b`
- Distribution version observed: `10.0.0`
- License observed in its pyproject: Apache-2.0, with LICENSE and NOTICE.
- Usage: separately installed dependency; public Python contracts and MenuBackend
  protocol are used by original adapter code. The upstream source tree, bridge,
  LICENSE and NOTICE are NOT vendored in this archive. pip must install the exact
  source revision and retain its own notices. No upstream commit or PR was made.

## Other discussed repositories

https://github.com/Bees-D/Fl-Studio-Ai-Producer and
https://github.com/IzzoSol/FL-STUDIO-AI were integration/design references. Their
controller/audio implementations were not copied into this build. No redistribution
permission is assumed for an unlicensed repository. Original deterministic MIDI,
measuring, preview and execution code replaces rather than wraps copied routines.

## Runtime dependencies

NumPy, SciPy, python-soundfile/libsndfile, pyloudnorm, Pydantic, imageio-ffmpeg,
PostFader's dependency tree, optional pywinauto/psutil and an optionally configured
llama.cpp executable remain separately licensed software. Installing requirements
retrieves them from the configured package sources. This archive does not bundle
their wheels, native binaries, source licenses, or model weights. For a future
binary redistribution, collect exact transitive licenses, FFmpeg build licensing,
notices, model terms and an SBOM first; this source release is not that audit.

No proprietary plugins, FL Studio installer, Image-Line assets, sound samples,
MIDI drivers, fonts, cloud credentials, private project files or AI weights are
included. FL Studio and related names belong to their respective owners.

## Source documentation used for the implementation

- Image-Line MIDI scripting:
  https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm
- Image-Line export documentation:
  https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/fformats_save_export.htm
- FFmpeg filters / loudnorm: https://ffmpeg.org/ffmpeg-filters.html#loudnorm
- pyloudnorm: https://github.com/csteinmetz1/pyloudnorm
- pywinauto menu wrappers:
  https://pywinauto.readthedocs.io/en/latest/code/pywinauto.controls.menuwrapper.html
- llama.cpp server: https://github.com/ggml-org/llama.cpp/tree/master/tools/server
- MCP stdio / transport documentation:
  https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

These references establish documented APIs, not live-host validation of this app.
