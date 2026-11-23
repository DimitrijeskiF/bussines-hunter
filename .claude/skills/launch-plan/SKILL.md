---
name: launch-plan
description: Turn one ranked Business Hunter idea into a staged Launch Plan - product, design, build, sales, money and legal, critic and roadmap - and save the PDF to ~/Desktop/Business Hunter.
argument-hint: "[rank or idea id] [notes] [--fresh]"
disable-model-invocation: true
---

# Business Hunter: plan one idea

You are the orchestrator. You do not plan yourself. You start agents, check their
output with the script, and finish with the PDF. Follow the steps in order, from the
project root.

Arguments typed after /launch-plan: `$ARGUMENTS`

## Step 1: start the plan

Run `python3 scripts/plan.py start --raw "<the arguments above, verbatim>"`
(escape any double quotes; use `--raw ""` if there are none). It prints JSON with a
`status`. If it fails, tell the user the error in one line and stop.

- `pick_idea`: show the listed ideas (rank, title, score), ask which one to plan, and
  stop. When the user answers, run step 1 again with their choice.
- `profile_missing`: ask the user all the `questions` in one message, numbered, plus
  "Anything else that helps (contacts, an existing company, experience)?". When they
  answer, write `data/founder.json` yourself with the fields `builder`,
  `hours_per_week`, `budget_six_months`, `country`, `languages`, `goal` and, if given,
  `extra`. Write every answer as text, in the user's words. Run
  `python3 scripts/plan.py validate-profile`, fix what it reports, then run step 1 again.
- `needs_deepdive`: launch one `deep-diver` with `idea_id: <idea_id>`,
  `run_dir: <run_dir>`, `quick: false`. Then run step 1 again. If the status is still
  `needs_deepdive`, stop and tell the user.
- `ready`: note `plan_dir` and continue.

Every agent below is prompted with one line: `plan_dir: <plan_dir>`.

## Step 2: product planner

Launch `product-planner`. Wait for it.

- If its reply says `search refused: yes`, stop here. Tell the user that web search is
  used up in this session and that they should open a new session and type the same
  command again. Do not start the other agents.
- Run `python3 scripts/plan.py validate product <plan_dir>`. On errors, launch it once
  more with: "Your previous file failed validation. Read <plan_dir>/parts/product.json,
  fix these errors and write it again:" and the error lines. Validate again. If it still
  fails, stop and tell the user: nothing can be planned without the stages.

## Step 3: design, build and sales, in parallel

In ONE message, launch `design-planner`, `build-planner` and `sales-planner`. Wait for
all three. Run `python3 scripts/plan.py validate parts <plan_dir>`.
- For each part with ERROR lines, re-launch its planner (all in one message) with the
  validation sentence from step 2, its own file name and its error lines.
- Then run `python3 scripts/plan.py validate parts <plan_dir> --skip-invalid`. Parts
  that are still invalid are left out.

## Step 4: money planner

Launch `money-planner`. Run `python3 scripts/plan.py validate money <plan_dir>`. On
errors, re-launch it once with the error lines, then run
`python3 scripts/plan.py validate money <plan_dir> --skip-invalid`.

## Step 5: critic

Launch `plan-critic`. Run `python3 scripts/plan.py validate critic <plan_dir>`. On
errors, re-launch it once with the error lines, then run
`python3 scripts/plan.py validate critic <plan_dir> --skip-invalid`.

## Step 6: one round of fixes

Run `python3 scripts/plan.py fixes <plan_dir>`. It prints `fixes` (lines per part) and
`order` (batches). If `order` is empty, go to step 7.

For each batch in order, launch the planners of that batch in ONE message, each with
its usual prompt plus: "The critic found these problems in your part. Read your file,
fix exactly these and write it again:" and that part's lines. Wait for the batch.

Then validate as in steps 3 and 4: `validate parts`, one retry with error lines,
`validate parts --skip-invalid`; and the same for `validate money` if money was fixed.
A part whose fixed version still fails is replaced by its earlier version (the script
prints KEPT). The critic does not run again.

## Step 7: plan lead

Launch `plan-lead`. Run `python3 scripts/plan.py validate roadmap <plan_dir>`. On
errors, re-launch it once with the error lines, then run
`python3 scripts/plan.py validate roadmap <plan_dir> --skip-invalid` and continue even
if the roadmap was left out.

## Step 8: report

Run `python3 scripts/plan.py finalize <plan_dir>`. It prints the PDF path, the verdict,
the stage names, the first actions for this week and what was left out.

## Step 9: tell the user

Reply in plain, short language: the verdict, one line per stage, the first three
actions for this week, and the PDF path. For a `stop` verdict give the verdict, the
reason and what would change it, with no stages and no action list. Mention anything
that was left out, kept from before the critic's fixes, or could not be checked. Do not
paste JSON, and do not ask the user to open any file other than the PDF.

## Rules

- Never write or edit the agents' JSON files yourself. Agents write them; the script
  checks them. The one file you write is `data/founder.json`, from the user's answers.
- Never skip a validation step.
- If something fails twice, leave it out, continue, and mention it at the end. A
  partial plan beats no plan. The product part is the exception: without it, stop.
- If an agent after the product planner reports `search refused: yes`, continue; its
  file lists what it could not check and the PDF shows it. Tell the user at the end
  that a new session gives a fuller plan.
- If the user asks to change their profile, ask the questions again, write
  `data/founder.json` and run `validate-profile`.
