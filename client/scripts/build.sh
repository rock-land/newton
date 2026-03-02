#!/bin/bash
set -e
cd "$(dirname "$0")/.."

mkdir -p public/dist
cp src/main.js public/dist/main.js

# in future this could be a bundler like esbuild/vite
