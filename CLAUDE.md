# Business Hunter harness

Multi-agent research pipeline that hunts worldwide for missing digital products that
ordinary people, freelancers or one-person shops would pay $1-3 a month for. Both kinds
of gap count: missing everywhere, or working in some countries but missing in others.

## The user reads PDFs only

The owner does not use an IDE and does not read Markdown or JSON. Every result must
end up as a PDF in `~/Desktop/Business Hunter/`. In chat, summarise in plain language
and point to the PDF; never ask them to open other files.

## Running

- `/hunt [theme] [--regions europe,africa] [--quick]` runs the full pipeline
  (see `.claude/skills/hunt/SKILL.md`).
- Weekly unattended runs: `scripts/run_weekly.sh`, scheduled by
  `scripts/install_schedule.sh` (macOS launchd; not installed by default).
- Tests: `python3 -m unittest discover -s tests`.

## Layout

- `.claude/agents/`: region-scout (one per region), synthesizer, scorer, skeptic, deep-diver.
- `config/`: `regions.toml`, `rubric.toml` (checks and their weights),
  `exclusions.toml`.
- `scripts/hunt.py`: deterministic steps (new-run, validate, rank, finalize).
  `scripts/hunt_lib.py` holds the logic; `scripts/report.css` styles the PDF.
- `data/`: runtime only. `runs/<date>/` holds agent output, `ideas.json` tracks ideas
  across runs, `logs/` holds weekly-run logs.

## History

Until 8 Nov 2026 the harness hunted enterprise B2B ideas for SAP-scale buyers. The
owner switched it to cheap worldwide subscriptions. Old SAP-era data is kept in
`data/archive-sap/` and is not read by new hunts.
