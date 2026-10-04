#!/bin/bash
# Start Luga Assist 100% in the background (no terminal window needed)
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

PYTHONPATH=. python3 -m app.daemon start
