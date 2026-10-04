#!/bin/bash
# Forward to comprehensive installer
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
exec "$PROJECT_DIR/install.sh" "$@"
