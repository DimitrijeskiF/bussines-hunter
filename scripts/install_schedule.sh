#!/bin/zsh
# Schedules the weekly hunt with macOS launchd.
#   scripts/install_schedule.sh            # Mondays 07:00
#   scripts/install_schedule.sh 3 18 30    # weekday (0=Sun..6=Sat), hour, minute
# If the Mac is asleep at that time, launchd runs the job when it wakes.
set -eu
project="${0:A:h:h}"
weekday="${1:-1}"; hour="${2:-7}"; minute="${3:-0}"
label="com.businesshunter.weekly"
plist="$HOME/Library/LaunchAgents/$label.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$project/data/logs"
cat >"$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array><string>/bin/zsh</string><string>-lc</string><string>'$project/scripts/run_weekly.sh'</string></array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>$weekday</integer>
    <key>Hour</key><integer>$hour</integer>
    <key>Minute</key><integer>$minute</integer>
  </dict>
  <key>StandardOutPath</key><string>$project/data/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$project/data/logs/launchd.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "Weekly hunt scheduled (weekday $weekday at $hour:$(printf %02d "$minute")). Plist: $plist"
