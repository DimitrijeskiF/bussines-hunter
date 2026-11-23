# Business Hunter

Business Hunter is a team of AI agents that runs inside
[Claude Code](https://claude.com/claude-code). It searches the web, region by region,
for digital products that are missing: things that ordinary people, freelancers or
one-person shops would pay $1-3 a month for. Two kinds of gap count: missing
everywhere, or working in some countries and missing in others.

You type one command and you get one PDF.

| Command | What it does | What you get |
|---|---|---|
| `/hunt` | Finds, scores and ranks ideas worldwide | A Hunt Report PDF |
| `/launch-plan` | Turns one idea you picked into a staged plan | A Launch Plan PDF |

Both PDFs are saved in `Desktop/Business Hunter/`.

## What you need

- Claude Code, signed in.
- Python 3.11 or newer. No extra packages.
- Google Chrome, Brave, Edge or Chromium. The PDF is printed with it.

Built and used on macOS. The weekly schedule works on macOS only.

## Set up

```bash
git clone https://github.com/DimitrijeskiF/bussines-hunter.git
cd bussines-hunter
claude
```

Then type `/hunt`. The project's settings already allow what a hunt needs: web
search, reading web pages, and writing inside the `data/` folder.

## Find ideas: `/hunt`

```
/hunt
/hunt study tools
/hunt freelancers --regions europe,africa
# Business Hunter

Business Hunter is a team of AI agents that runs inside
[Claude Code](https://claude.com/claude-code). It searches the web, region by region,
for digital products that are missing: things that ordinary people, freelancers or
one-person shops would pay $1-3 a month for. Two kinds of gap count: missing
everywhere, or working in some countries and missing in others.

You type one command and you get one PDF.

| Command | What it does | What you get |
|---|---|---|
| `/hunt` | Finds, scores and ranks ideas worldwide | A Hunt Report PDF |
| `/launch-plan` | Turns one idea you picked into a staged plan | A Launch Plan PDF |

Both PDFs are saved in `Desktop/Business Hunter/`.

## What you need

- Claude Code, signed in.
- Python 3.11 or newer. No extra packages.
- Google Chrome, Brave, Edge or Chromium. The PDF is printed with it.

Built and used on macOS. The weekly schedule works on macOS only.

## Set up

```bash
git clone https://github.com/DimitrijeskiF/bussines-hunter.git
cd bussines-hunter
claude
```

Then type `/hunt`. The project's settings already allow what a hunt needs: web
search, reading web pages, and writing inside the `data/` folder.

## Find ideas: `/hunt`

```
/hunt
/hunt study tools
/hunt freelancers --regions europe,africa
/hunt pet owners --quick
```

- **Theme** (optional): any text. Without one, the agents look at everything.
- **`--regions`** (optional): a comma-separated list. Without it, all eight regions
  are searched: `north_america`, `latin_america`, `europe`, `middle_east`, `africa`,
  `south_asia`, `east_asia`, `southeast_asia_oceania`.
- **`--quick`** (optional): a shorter, cheaper run. At most 8 ideas after merging,
  and deep dives for the top 2 only.

A full hunt across all eight regions took about 45 minutes in a recent run.

### What happens

1. **Scouts.** One agent per region, all at the same time. Each writes its findings
   with links to the pages they came from.
2. **Synthesizer.** Merges the findings into at most 20 ideas and flags two patterns:
   a pain felt in many regions, and an idea already solved in one region but open
   in another.
3. **Scorer and skeptic.** The scorer gives each idea 1-5 on seven checks and applies
   the hard rules. The skeptic tries to kill each idea and marks it as survives,
   weakened or killed.
4. **Ranking.** A script turns the checks into a score from 0 to 100. Weakened ideas
   lose 15%. Killed ideas and ideas that break a hard rule are cut.
5. **Deep dives.** The top 5 ideas each get one: competitors, customer, first
   version, price, the numbers, how to get users, 10 places to find the first users,
   and risks.
6. **Report.** A script builds the PDF.

After every step a script checks what the agents wrote. An agent whose output fails
the check twice is left out, and the report says so.

### The eight checks

| Check | Question |
|---|---|
| Needed every month | Is this a monthly need or a one-off? |
| Audience size | How many people have the problem? |
| Will pay $1-3 | Is there proof that people pay for this? |
| Competition gap | How well do existing tools cover it? |
| Small-team buildable | Can 1-3 people ship a first version? |
| Cheap to run | Does the running cost per user fit the price? |
| Users without ads | Can it find users without paid ads? |
| Multi-region pull | In how many regions did the need show up? |

### What is in the Hunt Report

The top ideas, what changed since the last hunt, a deep dive for each top idea with
its scorecard and the skeptic's verdict, the other candidates, the ideas that were
cut and why, highlights per region, sources, and how the scoring works.

## Plan one idea: `/launch-plan`

> This command is being added on the `launch-plan-command` branch and is not in
> `main` yet.

```
/launch-plan
/launch-plan 1
/launch-plan 1 web only, start in one city
/launch-plan 1 --fresh
```

- **Nothing after the command:** it shows the top ideas of your latest hunt and asks
  which one to plan.
- **A number:** plans the idea with that rank in your latest hunt.
- **Text after the number:** notes for the planners.
- **`--fresh`:** starts from zero. Without it, planning the same idea again builds
  on the earlier plan, so names, stages and numbers stay stable.

The first time, it asks six short questions about you: who will build the product,
your hours a week, your budget for six months, your country, your languages and
your goal. The answers are remembered.

Run it in a new Claude Code session. A full hunt uses a lot of web searches, and the
planners need their own.

### The planning team

| Agent | What it works out |
|---|---|
| Product planner | Who it is for, the first market, and 3 to 5 stages |
| Designer | Name ideas, colours, sketches of the main screens |
| Build planner | The cheapest way to build it, tools, work per stage, running costs |
| Sales planner | Pitch, prices, channels, the first 30 days, support, keeping customers |
| Money and legal planner | Costs, income per stage, break-even, a legal checklist |
| Critic | Contradictions between the parts and weak assumptions |
| Plan lead | One roadmap, the verdict, and the decisions only you can make |

### Rules built into every plan

- **Prove it before building.** The first stage never builds software. It proves
  that people will pay, for example with a hand-run pilot.
- **An honest verdict.** Start, Start with caution, or Do not start.
- **A stop rule for every stage.** Each stage says when to continue and when to stop.
- **Nothing invented.** Each section lists what could not be checked.

It does not write the product's code, make real design files, give legal or tax
advice, or plan how to raise money from investors.

## Weekly hunts without you (macOS)

```bash
scripts/install_schedule.sh     # start the weekly schedule
scripts/uninstall_schedule.sh   # stop it
scripts/run_weekly.sh           # run one unattended hunt now
```

Two optional settings for `run_weekly.sh`:

```bash
HUNT_ARGS="study tools --quick" BH_MAX_BUDGET_USD=20 scripts/run_weekly.sh
```

- `HUNT_ARGS`: the text passed to `/hunt`.
- `BH_MAX_BUDGET_USD`: stops the run if spending passes this amount.

You get a desktop notification when the report is ready. Logs are in `data/logs/`.

## Change how it works

| File | What it controls |
|---|---|
| `config/regions.toml` | The regions and what each scout covers |
| `config/rubric.toml` | The weight of each check, how many ideas get a deep dive, the penalty for weakened ideas |
| `config/exclusions.toml` | The hard rules that cut an idea |

Environment variables: `BH_OUTPUT_DIR` (where PDFs are saved), `BH_DATA_DIR` (where
run data is kept) and `BH_BROWSER` (the path to the browser that prints the PDF).

## Folder layout

```
.claude/agents/   the agents: scouts, synthesizer, scorer, skeptic, deep-diver, planners
.claude/skills/   the commands: hunt and launch-plan
config/           regions, scoring weights, hard rules
scripts/          checks, ranking, PDF, weekly-run scripts
tests/            unit tests
data/             your results (created on the first run, never uploaded)
```

Inside `data/`: `runs/` holds each hunt, `ideas.json` tracks ideas across hunts,
`plans/` holds launch plans, `founder.json` holds your profile answers, and `logs/`
holds weekly-run logs.

## Tests

```bash
python3 -m unittest discover -s tests
```

## If something goes wrong

- **"No Chrome-based browser found":** install Google Chrome, or set `BH_BROWSER`.
- **"Unknown region":** use the region names listed above.
- **No PDF:** the same report is saved as `report.html` in the run's folder.
- **"Operation not permitted" on macOS:** allow your terminal or Claude Code to use
  the Desktop folder under System Settings, Privacy & Security, Files and Folders.

## Good to know

- This is desk research by AI agents. Check the key facts and talk to real users
  before you commit to an idea.
- Your results stay on your machine. The `data/` folder is never uploaded to GitHub.

Three things to know before you paste it:

- /launch-plan is ahead of GitHub. That command's code is still only on your machine, so the README carries a one-line note saying it is not in main yet. I'll remove the note when the branch is merged.
- Two details I could not check without folder access: the day and time of the weekly schedule (so I left it out), and anything specific your current README says about setup.
- The last troubleshooting line is general macOS advice for that error. It is the same fix I suggested for this session, and it has not been confirmed here yet.

Once the Desktop folder is unblocked, I'll save the same text into the project so your machine and GitHub match.
