#!/bin/bash
set -e
cd "$(dirname "$0")/.."

mkdir -p public/dist

# Scaffold build script — future bundler (esbuild/vite) will compile main.tsx here.
# See Stage 6 (Client Web UI) for planned React+TypeScript build pipeline.
