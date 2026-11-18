#!/bin/zsh
# Removes the weekly hunt schedule.
set -eu
label="com.businesshunter.weekly"
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$label.plist"
echo "Weekly hunt schedule removed."
