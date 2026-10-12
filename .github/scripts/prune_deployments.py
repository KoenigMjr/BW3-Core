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

@file:        prune_deployments.py
@date:        12.10.2026
@author:      KoenigMjr
@description: Deletes old deployments of an environment (default: github-pages)

A deployment is only deleted if ALL of the following apply:
  - it is not among the newest --keep-last deployments of the environment,
  - it is not the newest successful deployment (that is the live page),
  - its latest status is a finished one (never queued, pending or in_progress; unknown states also stay).

GitHub only deletes inactive deployments. So a deployment that is not inactive yet first gets the status
'inactive', then it is deleted. This only touches the entries in the deployment history, never the live page.

With --dry-run nothing is changed, the script only shows what would be deleted.
--max-deletions limits the deletions per call (GitHub API rate limit), the rest follows on the next call.

The script calls the GitHub CLI (gh), which is preinstalled on the GitHub runners.
It reads the token from the environment variable GH_TOKEN.
"""
import argparse
import json
import os
import subprocess
import sys
import time

# shared helpers of the run cleanup (same folder)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prune_runs import parse_time, write_summary

LIVE = "success"
INACTIVE = "inactive"
# Only these latest states may be deleted. None = deployment without any status.
# Everything else (queued, pending, in_progress or anything unknown) stays.
DELETABLE = {None, INACTIVE, LIVE, "failure", "error"}

LIST_JQ = ".[] | {id, environment, created_at, sha}"


def order_newest_first(deployments):
    r"""!Deployments with a readable date, newest first (ties: higher id is newer)

    A deployment without a readable date is left out: when in doubt, it stays."""
    readable = []
    for deployment in deployments:
        created = parse_time(deployment.get("created_at"))
        if created is not None:
            readable.append((created, deployment["id"], deployment))
    readable.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [deployment for _, _, deployment in readable]


def select_deployments_to_delete(deployments, keep_last, get_state, limit=None):
    r"""!Select the deployments that may be deleted, oldest first

    @param deployments: list of deployment dicts from the GitHub API
    @param keep_last: this many newest deployments are kept
    @param get_state: function deployment -> latest status state (or None)
    @param limit: stop after this many selected deployments (None = unlimited)
    @return (list of (deployment, state), number of older deployments not checked because of the limit)"""
    ordered = order_newest_first(deployments)
    states = {}

    def state_of(deployment):
        if deployment["id"] not in states:
            states[deployment["id"]] = get_state(deployment)
        return states[deployment["id"]]

    live_id = next((d["id"] for d in ordered if state_of(d) == LIVE), None)

    # oldest first, so with a limit the oldest ones go first
    older = list(reversed(ordered[keep_last:]))
    selected = []
    for position, deployment in enumerate(older):
        if limit is not None and len(selected) >= max(limit, 0):
            return selected, len(older) - position
        if deployment["id"] == live_id:
            continue
        state = state_of(deployment)
        if state in DELETABLE:
            selected.append((deployment, state))
    return selected, 0


def gh(args, runner):
    r"""!Call the GitHub CLI, raises RuntimeError if it is missing"""
    try:
        return runner(["gh", "api", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("GitHub CLI (gh) not found") from None


def fetch_deployments(repo, environment, runner=subprocess.run):
    r"""!All deployments of the environment (raises RuntimeError on failure)"""
    result = gh(["--paginate", f"repos/{repo}/deployments?environment={environment}&per_page=100", "--jq", LIST_JQ], runner)
    if result.returncode != 0:
        raise RuntimeError(f"Could not read the deployments: {result.stderr.strip() or result.stdout.strip()}")
    deployments = []
    for number, line in enumerate(result.stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            deployment = json.loads(line)
        except json.JSONDecodeError:
            raise RuntimeError(f"Unexpected response from GitHub in line {number}: {line[:80]!r}") from None
        if not isinstance(deployment, dict) or "id" not in deployment:
            raise RuntimeError(f"Unexpected response from GitHub in line {number}: {line[:80]!r}")
        deployments.append(deployment)
    return deployments


def fetch_state(repo, deployment_id, runner=subprocess.run):
    r"""!Latest status state of a deployment, None if it has no status (raises RuntimeError on failure)"""
    result = gh([f"repos/{repo}/deployments/{deployment_id}/statuses?per_page=1"], runner)
    if result.returncode != 0:
        raise RuntimeError(f"Could not read the status of deployment {deployment_id}: "
                           f"{result.stderr.strip() or result.stdout.strip()}")
    try:
        statuses = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        raise RuntimeError(f"Unexpected status response for deployment {deployment_id}: {result.stdout[:80]!r}") from None
    if not isinstance(statuses, list):
        raise RuntimeError(f"Unexpected status response for deployment {deployment_id}: {result.stdout[:80]!r}")
    return statuses[0].get("state") if statuses and isinstance(statuses[0], dict) else None


def delete_deployment(repo, deployment_id, state, runner=subprocess.run):
    r"""!Mark the deployment inactive (if needed), then delete it

    @return (True, '') or (False, reason)"""
    if state != INACTIVE:
        result = gh(["-X", "POST", f"repos/{repo}/deployments/{deployment_id}/statuses", "-f", f"state={INACTIVE}"], runner)
        if result.returncode != 0:
            return False, "set inactive: " + (result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}")
    result = gh(["-X", "DELETE", f"repos/{repo}/deployments/{deployment_id}"], runner)
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}")


def describe(deployment, state):
    r"""!Short readable description of a deployment for the log"""
    created = (deployment.get("created_at") or "")[:10]
    sha = (deployment.get("sha") or "")[:7]
    return f"deployment {deployment['id']} ({created}, {sha or 'no sha'}, {state or 'no status'})"


def main(argv=None, runner=subprocess.run, sleep=time.sleep):
    r"""!Entry point

    @return 0 = ok, 1 = at least one deletion failed, 2 = deployments could not be read"""
    parser = argparse.ArgumentParser(description="Deletes old deployments of an environment.")
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--environment", default="github-pages", help="environment name (github-pages)")
    parser.add_argument("--keep-last", type=int, default=5, help="this many newest deployments are kept (5, at least 1)")
    parser.add_argument("--max-deletions", type=int, default=100, help="at most this many deletions per call (100)")
    parser.add_argument("--dry-run", action="store_true", help="change nothing, only show")
    args = parser.parse_args(argv)
    if args.keep_last < 1:
        parser.error("--keep-last must be at least 1")
    if args.max_deletions < 0:
        parser.error("--max-deletions must not be negative")

    try:
        deployments = fetch_deployments(args.repo, args.environment, runner)
        chosen, unchecked = select_deployments_to_delete(
            deployments, args.keep_last, lambda d: fetch_state(args.repo, d["id"], runner), args.max_deletions)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    mode = "Dry run (nothing is changed)" if args.dry_run else "Delete"
    print(f"{mode}: {len(deployments)} deployments of '{args.environment}' found, {len(chosen)} of them selected "
          f"(the newest {args.keep_last} and the live one stay).")

    deleted, failed = [], []
    for deployment, state in chosen:
        if args.dry_run:
            print(f"  would delete: {describe(deployment, state)}")
            continue
        ok, reason = delete_deployment(args.repo, deployment["id"], state, runner)
        if ok:
            deleted.append(deployment)
            print(f"  deleted: {describe(deployment, state)}")
        else:
            failed.append(deployment)
            print(f"  ERROR at {describe(deployment, state)}: {reason}", file=sys.stderr)
        sleep(0.1)                                                           # go easy on the rate limit

    if unchecked:
        print(f"{unchecked} older deployment(s) not checked (limit: {args.max_deletions} per call): start again.")
    summary = [f"### Cleanup of deployments ({args.environment})", f"- Found: {len(deployments)}"]
    if args.dry_run:
        summary.append(f"- Dry run: {len(chosen)} would be deleted, nothing was changed")
    else:
        summary.append(f"- Deleted: {len(deleted)}")
        summary.append(f"- Not deleted (errors): {len(failed)}")
    summary.append(f"- Not checked yet (limit reached): {unchecked}")
    write_summary(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
