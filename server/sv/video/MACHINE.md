## This machine

A Linux container on the GPU machine, with its NVIDIA GPU, the network and the whole shell. This folder is yours; work in it.

- Node 24 and npm. `node_modules/` already has three.js (with `examples/jsm`), puppeteer, ws, harfbuzzjs and
  opentype.js; `npm install` anything else.
- Python 3.11 with numpy and Pillow, and pip: `pip install` anything (it lands in `.local/` here, so it's still there
  later). If `pip` is missing, `curl -sSL https://bootstrap.pypa.io/get-pip.py | python3 -` sets it up.
- The GPU, two ways: Chromium (puppeteer) draws WebGL on it when launched with
  `executablePath: process.env.PUPPETEER_EXECUTABLE_PATH` and `args: process.env.SV_CHROME_ARGS.split(' ')` (without
  those it falls back to software rendering, about ten times slower), and native OpenGL through EGL (for example
  moderngl's `create_standalone_context(backend="egl")`).
- ffmpeg and ffprobe, with libx264, libx265, NVENC and ProRes.
- `fonts/`: about ninety open-licensed typefaces. Any other face can come from the web.

You can see any image you render. Long renders can run in the background while you check on them.
