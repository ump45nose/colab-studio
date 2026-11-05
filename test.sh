#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
./lint.sh
cd server/web
npm install --silent
npm run build --silent
npx playwright test
cd ../..
uv run -q --python 3.12 --with-requirements server/requirements.txt --with pytest --with pytest-asyncio pytest -q
