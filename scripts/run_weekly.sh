#!/bin/zsh
# Runs a Business Hunter hunt with nobody at the keyboard, then shows a macOS
# notification. launchd starts it weekly (see install_schedule.sh); you can also
# run it by hand.
#
# Optional environment variables:
#   HUNT_ARGS          text passed to /hunt, e.g. "--quick" or "ESG reporting"
#   BH_MAX_BUDGET_USD  stop the run if API spend passes this amount
set -u
cd "${0:A:h}/.."

mkdir -p data/logs
log="data/logs/$(date +%Y-%m-%d_%H%M).log"
claude_bin="$(command -v claude || echo "$HOME/.local/bin/claude")"

# Make the main agent wait for every sub-agent before the run ends.
export CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0

budget=()
[[ -n "${BH_MAX_BUDGET_USD:-}" ]] && budget=(--max-budget-usd "$BH_MAX_BUDGET_USD")

if "$claude_bin" -p "/hunt ${HUNT_ARGS:-}" \
    --permission-prompts none \
    --allowedTools "WebSearch" "WebFetch" "Read" "Edit(./data/**)" "Bash(python3 scripts/hunt.py *)" \
    "${budget[@]}" >"$log" 2>&1; then
  osascript -e 'display notification "New report saved in Desktop > Business Hunter" with title "Business Hunter"' 2>/dev/null
else
  osascript -e 'display notification "The weekly hunt failed. Ask Claude to check the log." with title "Business Hunter"' 2>/dev/null
  exit 1
fi
