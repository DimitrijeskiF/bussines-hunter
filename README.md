# Business Hunter

A multi-agent research pipeline for [Claude Code](https://claude.com/claude-code).
It searches the world, region by region, for missing digital products that ordinary
people, freelancers or one-person shops would pay $1-3 a month for. It then scores
each idea, tries to knock it down, digs deeper into the best ones, and saves the
result as a PDF report.

Two kinds of gap count:

- a product that is missing everywhere, and
- a product that works in some countries but is missing in others.

## What you need

- Claude Code, with web search available
- Python 3.11 or newer (no extra packages to install)
- Google Chrome or Chromium, which is used to print the PDF
- macOS, if you want the optional weekly schedule

Built and used on macOS.

## Quick start

```sh
git clone https://github.com/DimitrijeskiF/bussines-hunter.git
cd bussines-hunter
claude
```

Then type this into Claude Code:

```
/hunt --quick
```

When the hunt finishes, the report is in `~/Desktop/Business Hunter/`, named like
`2026-11-23 Hunt Report.pdf`.

## Hunt options

```
/hunt [theme] [--regions a,b] [--quick]
```

| What you type | What happens |
|---|---|
| `/hunt` | Full worldwide hunt across all eight regions |
| `/hunt --quick` | Faster, cheaper run with fewer searches |
| `/hunt pet owners` | Same hunt, focused on a theme of your choice |
| `/hunt --regions europe,africa` | Only the regions you name |
| `/hunt freelancers --regions latin_america,south_asia --quick` | All three combined |

Full and quick runs differ like this:

| | Full | Quick |
|---|---|---|
| Findings per region | 6-10 | 3-4 |
| Ideas kept after merging | up to 20 | up to 8 |
| Deep dives | top 5 | top 2 |

Region names for `--regions`:

| Id | Region |
|---|---|
| `north_america` | North America |
| `latin_america` | Latin America |
| `europe` | Europe |
| `middle_east` | Middle East |
| `africa` | Africa |
| `south_asia` | South Asia |
| `east_asia` | East Asia |
| `southeast_asia_oceania` | Southeast Asia + Oceania |

## How a hunt works

1. **Scouts.** One `region-scout` agent per region searches the web, all at the same
   time, and writes down what it finds with sources.
2. **Synthesizer.** Merges the regional findings into one list of ideas and marks the
   ones that show up in several regions.
3. **Scorer.** Scores every idea from 1 to 5 on seven checks, such as how often people
   feel the problem and whether anyone already pays for something similar.
4. **Skeptic.** Tries to kill every idea: free alternatives, big tech giving it away,
   reasons nobody would pay. Each idea survives, is weakened, or is killed.
5. **Ranking.** A script combines scores and verdicts and picks the top ideas.
6. **Deep dives.** One `deep-diver` agent per top idea covers competitors, customer,
   first version, price, numbers, and where to find the first users.
7. **Report.** A script builds the PDF.

A Python script checks every agent's output before the next step runs. Anything that
fails twice is left out and named in the report, so you still get a report.

## Cost and search limits

A full hunt starts 16 agents and runs a few hundred web searches. If your plan limits
web searches, the later steps end up with thinner research. To avoid that, start with
`--quick`, or hunt two or three regions at a time with `--regions`.

## Where results are kept

- **The report:** `~/Desktop/Business Hunter/`. Set `BH_OUTPUT_DIR` to change the folder.
- **Working files:** `data/`, created on the first hunt and ignored by git, so your
  results never end up in the repository. Set `BH_DATA_DIR` to move it.
  - `data/runs/<date>/` holds what the agents wrote during each hunt.
  - `data/ideas.json` remembers ideas across hunts. Later hunts add fresh evidence to
    known ideas, and each report shows what changed since the last one.

To start again from zero, delete the `data/` folder.

## Weekly unattended runs (macOS)

```sh
scripts/install_schedule.sh            # every Monday at 07:00
scripts/install_schedule.sh 3 18 30    # weekday (0 = Sunday .. 6 = Saturday), hour, minute
scripts/uninstall_schedule.sh          # switch it off
```

The schedule is not installed by default. A macOS notification tells you when the
report is ready. You can also run a hunt unattended by hand:

```sh
HUNT_ARGS="--quick" BH_MAX_BUDGET_USD=20 scripts/run_weekly.sh
```

`HUNT_ARGS` is the text you would type after `/hunt`. `BH_MAX_BUDGET_USD` stops the
run if spending passes that amount.

## Make it yours

| File | What it controls |
|---|---|
| `config/regions.toml` | The regions, their countries and languages, and hints for each scout |
| `config/rubric.toml` | The checks, their weights, and how many ideas get a deep dive |
| `config/exclusions.toml` | What gets rejected outright and what a good idea looks like |
| `.claude/agents/` | The instructions for each of the five agents |
| `.claude/skills/hunt/SKILL.md` | The steps of the `/hunt` command |
| `scripts/report.css` | The look of the PDF |

## Tests

```sh
python3 -m unittest discover -s tests
```
