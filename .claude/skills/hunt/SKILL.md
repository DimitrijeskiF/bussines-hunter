---
name: hunt
description: Run a Business Hunter research hunt - regional scout agents, synthesis, scoring, skeptic review and deep dives - and save the PDF report to ~/Desktop/Business Hunter.
argument-hint: "[theme] [--regions europe,africa] [--quick]"
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/hunt.py *), Read
---

# Business Hunter: run a hunt

You are the orchestrator. You do not research yourself. You start agents, check their
output with the script, and finish with the PDF. Follow the steps in order, from the
project root.

Arguments typed after /hunt: `$ARGUMENTS`

## Step 1: start the run

Run `python3 scripts/hunt.py new-run --raw "<the arguments above, verbatim>"`
(escape any double quotes; use `--raw ""` if there are none).

It prints JSON with `run_dir`, `theme`, `quick`, `max_clusters` and `regions`. If it
fails (for example an unknown region), tell the user the error in one line and stop.

## Step 2: regional scouts, in parallel

In ONE message, launch one `region-scout` agent per region from step 1, so they all
run at the same time. Prompt for each:

```
region: <id>
region_name: <name>
run_dir: <run_dir>
theme: <theme, or "none">
quick: <true|false>
```

Wait until every scout has finished before you continue.

Run `python3 scripts/hunt.py validate cards <run_dir>`.
- For regions with ERROR lines, launch a new `region-scout` for each of them (in one
  message), with the same prompt plus: "Your previous file failed validation. Read
  <run_dir>/cards/<id>.json, fix these errors and write it again:" followed by that
  region's error lines. Wait for them.
- Then run `python3 scripts/hunt.py validate cards <run_dir> --skip-invalid`. Regions
  that are still invalid are left out. If the command fails (no valid region), stop
  and tell the user.

## Step 3: synthesizer

Launch one `synthesizer` agent with `run_dir: <run_dir>`. Wait for it.

Run `python3 scripts/hunt.py validate clusters <run_dir>`. On errors, launch the
synthesizer once more with the error lines, asking it to fix clusters.json, then
validate again. If it still fails, stop and tell the user.

## Step 4: scorer and skeptic, in parallel

In ONE message, launch `scorer` and `skeptic`, each with:

```
run_dir: <run_dir>
quick: <true|false>
```

Wait for both. Run `python3 scripts/hunt.py validate review <run_dir>`. Errors
labelled `scores.json` mean re-launch the scorer with those errors; errors labelled
`skeptic.json` mean re-launch the skeptic. Validate again. If it still fails, stop and
tell the user.

## Step 5: rank

Run `python3 scripts/hunt.py rank <run_dir>`. It prints the `top` idea ids. If `top`
is empty, skip step 6.

## Step 6: deep dives, in parallel

In ONE message, launch one `deep-diver` per top id:

```
idea_id: <id>
run_dir: <run_dir>
quick: <true|false>
```

Wait for all of them. Run `python3 scripts/hunt.py validate deepdives <run_dir>`. For
each failed id, re-launch a `deep-diver` once with its error lines (all in one
message). Then run `python3 scripts/hunt.py validate deepdives <run_dir> --skip-invalid`.

## Step 7: report

Run `python3 scripts/hunt.py finalize <run_dir>`. It prints the PDF path and the top
ideas.

## Step 8: tell the user

Reply in plain, short language: the top ideas (rank, title, score) and the PDF path.
Mention any region or deep dive that failed. Do not paste JSON, and do not ask the user
to open any file other than the PDF. End with one line: to plan one of these, open a new
session and type /launch-plan and its rank.

## Rules

- Never write or edit the JSON files yourself. Agents write them; the script checks them.
- Never skip a validation step.
- If something fails twice, leave it out, continue, and mention it at the end. A
  partial report beats no report.
