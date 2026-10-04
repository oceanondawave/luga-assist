#!/bin/bash
# Install Luga Assist as an automated macOS user LaunchAgent daemon
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_PATH="$HOME/Library/LaunchAgents/com.luga.assist.plist"
PYTHON_BIN="$(which python3)"

mkdir -p "$HOME/Library/LaunchAgents"

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.luga.assist</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>-m</string>
        <string>app.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$DIR</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$DIR/logs/luga_assist.log</string>
    <key>StandardErrorPath</key>
    <string>$DIR/logs/luga_assist.log</string>
</dict>
</plist>
EOF

echo "✅ Đã tạo file cấu hình LaunchAgent tại: $PLIST_PATH"
echo "👉 Để kích hoạt tự chạy ngầm khi mở máy: launchctl load -w $PLIST_PATH"
echo "👉 Để gỡ bỏ tự chạy ngầm:               launchctl unload -w $PLIST_PATH"
