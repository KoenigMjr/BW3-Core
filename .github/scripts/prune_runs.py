#!/usr/bin/python
# -*- coding: utf-8 -*-
r"""!
    ____  ____  ______       __      __       __       _____
   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
  / __  / / / /\__ \| | /| / / __ `/ __/ ___/ __ \     /_ <
 / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
                German BOS Information Script
                     by Bastian Schroll

@file:        prune_runs.py
@date:        12.10.2026
@author:      KoenigMjr
@description: Deletes old GitHub Actions workflow runs (including their logs and artifacts)

A run is only deleted if ALL of the following apply:
  - it is completed (never a running, queued, waiting or requested run),
  - it is older than --keep-days days,
  - it is not among the newest --keep-per-workflow runs of its workflow
    (so rarely running workflows always keep some history),
  - it is not the run that executes this script.

With --dry-run nothing is deleted, the script only shows what would be deleted.
--max-deletions limits the deletions per call (GitHub API rate limit), the rest follows on the next call.

The script calls the GitHub CLI (gh), which is preinstalled on the GitHub runners.
It reads the token from the environment variable GH_TOKEN.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

# Everything that is not 'completed' is still running or waiting: never touch it.
FINISHED = "completed"

# gh api --paginate returns one object per page. --jq turns it into one line (JSON) per run.
LIST_JQ = ".workflow_runs[] | {id, workflow_id, name, created_at, status, conclusion}"


def parse_time(value):
    r"""!Parse a GitHub ISO timestamp ('2026-10-12T09:23:51Z') as UTC time

    @param value: timestamp string
    @return datetime with timezone or None if not readable"""
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def select_runs_to_delete(runs, now, keep_days, keep_per_workflow, current_run_id=None, limit=None):
    r"""!Select the runs that may be deleted, oldest first, at most limit runs

    A run without a readable date is never selected: when in doubt, it stays.

    @param runs: list of run dicts from the GitHub API
    @param now: current time (datetime with timezone)
    @param keep_days: runs younger than this are kept
    @param keep_per_workflow: this many newest runs per workflow are kept
    @param current_run_id: id of the running job (never selected)
    @param limit: maximum number of selected runs (None = unlimited)
    @return list of run dicts"""
    cutoff = now - dt.timedelta(days=keep_days)
    by_workflow = {}
    for run in runs:
        created = parse_time(run.get("created_at"))
        if created is not None:
            by_workflow.setdefault(run.get("workflow_id"), []).append((created, run["id"], run))

    candidates = []
    for items in by_workflow.values():
        items.sort(key=lambda item: (item[0], item[1]), reverse=True)        # newest first
        for position, (created, run_id, run) in enumerate(items):
            if position < keep_per_workflow:
                continue                                                      # among the newest: stays
            if run.get("status") != FINISHED or created >= cutoff or run_id == current_run_id:
                continue
            candidates.append((created, run_id, run))

    candidates.sort(key=lambda item: (item[0], item[1]))                      # oldest first
    selected = [run for _, _, run in candidates]
    return selected if limit is None else selected[:max(limit, 0)]


def fetch_runs(repo, runner=subprocess.run):
    r"""!Fetch all runs of the repository via the GitHub CLI

    @param repo: owner/repository
    @param runner: replacement for subprocess.run (for tests)
    @return list of run dicts (raises RuntimeError on failure)"""
    try:
        result = runner(["gh", "api", "--paginate", f"repos/{repo}/actions/runs?per_page=100", "--jq", LIST_JQ],
                        capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("GitHub CLI (gh) not found") from None
    if result.returncode != 0:
        raise RuntimeError(f"Could not read the runs: {result.stderr.strip() or result.stdout.strip()}")
    runs = []
    for number, line in enumerate(result.stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            run = json.loads(line)
        except json.JSONDecodeError:
            raise RuntimeError(f"Unexpected response from GitHub in line {number}: {line[:80]!r}") from None
        if not isinstance(run, dict) or "id" not in run:
            raise RuntimeError(f"Unexpected response from GitHub in line {number}: {line[:80]!r}")
        runs.append(run)
    return runs


def delete_run(repo, run_id, runner=subprocess.run):
    r"""!Delete one run

    @param repo: owner/repository
    @param run_id: id of the run
    @param runner: replacement for subprocess.run (for tests)
    @return (True, '') or (False, reason)"""
    result = runner(["gh", "api", "-X", "DELETE", f"repos/{repo}/actions/runs/{run_id}"], capture_output=True, text=True)
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}")


def describe(run):
    r"""!Short readable description of a run for the log"""
    created = (run.get("created_at") or "")[:10]
    return f"{run.get('name') or 'Workflow ' + str(run.get('workflow_id'))} (run {run['id']}, {created})"


def write_summary(lines):
    r"""!Append the summary to the run page if GitHub provides a file for it"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main(argv=None, now=None, runner=subprocess.run, sleep=time.sleep):
    r"""!Entry point

    @return 0 = ok, 1 = at least one deletion failed, 2 = runs could not be read"""
    parser = argparse.ArgumentParser(description="Deletes old workflow runs.")
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--keep-days", type=float, default=30, help="runs younger than this many days are kept (30)")
    parser.add_argument("--keep-per-workflow", type=int, default=10, help="this many newest runs per workflow are kept (10)")
    parser.add_argument("--max-deletions", type=int, default=400, help="at most this many deletions per call (400)")
    parser.add_argument("--current-run-id", type=int, default=None, help="the running job (default: GITHUB_RUN_ID)")
    parser.add_argument("--dry-run", action="store_true", help="delete nothing, only show")
    args = parser.parse_args(argv)
    if args.keep_days < 0 or args.keep_per_workflow < 0 or args.max_deletions < 0:
        parser.error("Values must not be negative")

    now = now or dt.datetime.now(dt.timezone.utc)
    current = args.current_run_id
    if current is None and os.environ.get("GITHUB_RUN_ID", "").isdigit():
        current = int(os.environ["GITHUB_RUN_ID"])

    try:
        runs = fetch_runs(args.repo, runner)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    # Select without limit first: this way we can tell how many are left over.
    everything = select_runs_to_delete(runs, now, args.keep_days, args.keep_per_workflow, current)
    chosen = everything[:args.max_deletions]
    mode = "Dry run (nothing is deleted)" if args.dry_run else "Delete"
    print(f"{mode}: {len(runs)} runs found, {len(everything)} of them may be deleted "
          f"(older than {args.keep_days:g} days, not among the newest {args.keep_per_workflow} per workflow).")

    deleted, failed = [], []
    for run in chosen:
        if args.dry_run:
            print(f"  would delete: {describe(run)}")
            continue
        ok, reason = delete_run(args.repo, run["id"], runner)
        if ok:
            deleted.append(run)
            print(f"  deleted: {describe(run)}")
        else:
            failed.append(run)
            print(f"  ERROR at {describe(run)}: {reason}", file=sys.stderr)
        sleep(0.1)                                                           # go easy on the rate limit

    remaining = len(everything) - len(chosen)
    if remaining:
        print(f"{remaining} run(s) left for the next call (limit: {args.max_deletions} per call).")
    summary = ["### Cleanup of workflow runs", f"- Found: {len(runs)}"]
    if args.dry_run:
        summary.append(f"- Dry run: {len(chosen)} would be deleted, nothing was deleted")
    else:
        summary.append(f"- Deleted: {len(deleted)}")
        summary.append(f"- Not deleted (errors): {len(failed)}")
    summary.append(f"- Left for the next call: {remaining}")
    write_summary(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
