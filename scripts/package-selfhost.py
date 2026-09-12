"""Create a source release from an explicit allowlist, without operator state."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
trees = ['backend', 'db', 'src', 'public/covers', 'public/media', 'public/fonts',
         'public/visualizers', 'docs/upstream/yue2']
files = '''LICENSE README.md SELF_HOSTED.md SECURITY.md THIRD_PARTY_NOTICES.md .env.example .gitignore
public/favicon.svg package.json package-lock.json tsconfig.json vite.config.ts index.html visualizer-render.html'''.split()
files += [str(p.relative_to(root)) for p in (root/'deploy').iterdir() if p.is_file() and p.suffix in {'.py', '.json', '.in', '.yaml', '.apparmor'}]
files += [str(p.relative_to(root)) for p in (root/'scripts').iterdir() if p.is_file() and (p.name.startswith(('verify-', 'test-')) or p.name in {'dev-connected.mjs', 'package-selfhost.py', 'capture-studio.mjs'})]
files += ['scripts/video/'+name for name in '''visualizer-export-api.mjs visualizer-export-relay.mjs
visualizer-export-server.mjs visualizer-export-worker.mjs visualizer-analyze.mjs visualizer-render.mjs
visualizer-native.cpp build-visualizer-renderer.mjs compose-music-film.py verify-film.py'''.split()]
files += ['docs/backend/'+name for name in '''README.md OPERATIONS.md LOCAL_PROVIDERS.md ASSISTANCE.md
VIDEO_EDITOR.md VISUALIZER_EXPORT.md VISUALIZER_LIBRARY.md LEGION_VISUALIZER_RENDERER.md
CLASSIC_CREDITS.md submission.schema.json'''.split()]
for tree in trees:
    files.extend(str(p.relative_to(root)) for p in (root/tree).rglob('*') if p.is_file())
for tree in ['docs/licenses','docs/notices']:
    files.extend(str(p.relative_to(root)) for p in (root/tree).rglob('*') if p.is_file())
paths = sorted({name for name in files if not any(part.startswith('.') or part in {'__pycache__', 'node_modules', 'data', 'evidence'} for part in Path(name).parts) or name in {'.env.example', '.gitignore'}})
manifest = {}
args.output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(args.output, 'x', zipfile.ZIP_DEFLATED) as archive:
    for name in paths:
        path = root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Release source must not contain symlinks: '+name)
        # The archive opens on the portable installer guide, not historical
        # workspace-only evidence and production-project links.
        data = (root/'SELF_HOSTED.md').read_bytes() if name == 'README.md' else path.read_bytes()
        manifest[name] = hashlib.sha256(data).hexdigest()
        archive.writestr('sound-vision/'+name, data)
    archive.writestr('sound-vision/RELEASE_FILES.json', json.dumps(manifest, indent=2)+'\n')
digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
args.output.with_suffix(args.output.suffix+'.sha256').write_text(digest+'  '+args.output.name+'\n')
print(json.dumps({'archive':str(args.output.resolve()),'files':len(manifest),'bytes':args.output.stat().st_size,'sha256':digest}))
