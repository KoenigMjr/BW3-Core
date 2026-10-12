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

@file:        test_prune_runs.py
@date:        12.10.2026
@author:      KoenigMjr
@description: Unittests for BOSWatch. File have to run as "pytest" unittest

The script deletes, so these tests mainly pin down the protection rules: never a running or waiting run,
never the current run, never a run without a readable date, and the newest runs of every workflow always stay.
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import datetime as dt
import importlib.util
import json
import logging
import os
import random
import stat
import subprocess
import sys
import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "scripts", "prune_runs.py")
spec = importlib.util.spec_from_file_location("prune_runs", SCRIPT)
prune_runs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prune_runs)

NOW = dt.datetime(2026, 10, 12, 12, 0, 0, tzinfo=dt.timezone.utc)


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


def makeRun(runId, daysOld, workflow=1, status="completed"):
    r"""!A run that was started daysOld days ago"""
    created = NOW - dt.timedelta(days=daysOld)
    return {"id": runId, "workflow_id": workflow, "name": f"Workflow {workflow}",
            "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": status, "conclusion": "success"}


def makeRuns(count, firstAge, workflow=1, firstId=1):
    r"""!count runs with the ages firstAge, firstAge + 1, ... and consecutive ids"""
    return [makeRun(firstId + i, firstAge + i, workflow) for i in range(count)]


def ids(runs):
    return [run["id"] for run in runs]


def select(runs, keepDays=30, keepPerWorkflow=10, **kwargs):
    return prune_runs.select_runs_to_delete(runs, NOW, keepDays, keepPerWorkflow, **kwargs)


class FakeGh:
    r"""!Replaces subprocess.run: returns the runs and records which ones were deleted"""

    def __init__(self, runs, failIds=(), listFailure=None):
        self.runs = runs
        self.failIds = set(failIds)
        self.listFailure = listFailure
        self.deleted = []
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if "--paginate" in cmd:
            if self.listFailure:
                return subprocess.CompletedProcess(cmd, 1, "", self.listFailure)
            return subprocess.CompletedProcess(cmd, 0, "\n".join(json.dumps(r) for r in self.runs) + "\n", "")
        runId = int(cmd[-1].rsplit("/", 1)[1])
        if runId in self.failIds:
            return subprocess.CompletedProcess(cmd, 1, "", "HTTP 403: Forbidden")
        self.deleted.append(runId)
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture()
def summaryFile(tmp_path, monkeypatch):
    r"""!Provide a step summary file and make sure no GITHUB_RUN_ID leaks in"""
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    return path


@pytest.fixture()
def runMain(summaryFile):
    r"""!Run main() with a fake gh, returns (return code, sleeps)"""
    def _run(gh, *args):
        sleeps = []
        code = prune_runs.main(["--repo", "o/r", *args], now=NOW, runner=gh, sleep=sleeps.append)
        return code, sleeps
    return _run


# selection


def test_selectOldRunsBeyondNewest():
    r"""!Old finished runs beyond the newest ones are selected"""
    assert sorted(ids(select(makeRuns(15, 31)))) == [11, 12, 13, 14, 15]


def test_selectNeverYoungRuns():
    r"""!Runs younger than the cut-off are never selected"""
    assert select(makeRuns(20, 1)) == []


def test_selectKeepNewestEvenIfOld():
    r"""!The newest n are kept even if all of them are old"""
    assert sorted(ids(select(makeRuns(12, 100)))) == [11, 12]
    assert select(makeRuns(10, 100)) == []


def test_selectNewestCountedPerWorkflow():
    r"""!The newest runs are counted per workflow"""
    runs = makeRuns(12, 100, workflow=1, firstId=1) + makeRuns(3, 100, workflow=2, firstId=100)
    assert sorted(ids(select(runs))) == [11, 12]


@pytest.mark.parametrize("status", ["in_progress", "queued", "waiting", "requested", "pending", "unknown", None])
def test_selectNeverUnfinishedRuns(status):
    r"""!Runs that are not completed are never selected"""
    protected = [makeRun(100 + i, 40 + i) for i in range(10)]
    assert select(protected + [makeRun(1, 300, status=status)]) == []


def test_selectUnfinishedRunUsesProtectedSlot():
    r"""!An unfinished run still occupies one of the protected slots"""
    runs = [makeRun(1, 40, status="in_progress")] + makeRuns(10, 41, firstId=100)
    assert ids(select(runs)) == [109]


def test_selectNeverCurrentRun():
    r"""!The current run is never selected"""
    assert sorted(ids(select(makeRuns(15, 31), current_run_id=15))) == [11, 12, 13, 14]


def test_selectOldestFirst():
    r"""!The result is ordered oldest first"""
    assert ids(select(makeRuns(15, 31))) == [15, 14, 13, 12, 11]


def test_selectLimit():
    r"""!The limit keeps the oldest first, zero or negative selects nothing"""
    assert ids(select(makeRuns(15, 31), limit=2)) == [15, 14]
    assert select(makeRuns(15, 31), limit=0) == []
    assert select(makeRuns(15, 31), limit=-3) == []
    assert len(select(makeRuns(15, 31), limit=100)) == 5


def test_selectExactlyAtCutOff():
    r"""!Exactly at the cut-off stays, one second older goes"""
    atCutoff = makeRun(1, 30)
    older = dict(makeRun(2, 30), created_at=(NOW - dt.timedelta(days=30, seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert ids(select(makeRuns(10, 1, firstId=100) + [atCutoff, older])) == [2]


def test_selectNeverWithoutReadableDate():
    r"""!Runs without a readable date always stay and do not use a protected slot"""
    broken = [dict(makeRun(1, 500), created_at=None), dict(makeRun(2, 500), created_at="broken"),
              {k: v for k, v in makeRun(3, 500).items() if k != "created_at"}, dict(makeRun(4, 500), created_at=12345)]
    assert select(broken, keepPerWorkflow=0) == []
    runs = [dict(makeRun(1, 1), created_at="broken")] + makeRuns(11, 40, firstId=100)
    assert ids(select(runs)) == [110]


def test_selectOtherTimezoneOffset():
    r"""!Timestamps with another offset are compared correctly"""
    local = (NOW - dt.timedelta(days=29, hours=23)).astimezone(dt.timezone(dt.timedelta(hours=2)))
    assert select([dict(makeRun(1, 0), created_at=local.isoformat())], keepPerWorkflow=0) == []


def test_selectOrderOfInputIrrelevant():
    r"""!The order of the input does not matter, the input is not modified"""
    runs = makeRuns(15, 31) + makeRuns(12, 100, workflow=2, firstId=100)
    snapshot = [dict(r) for r in runs]
    expected = ids(select(runs))
    assert runs == snapshot
    for seed in range(5):
        shuffled = list(runs)
        random.Random(seed).shuffle(shuffled)
        assert ids(select(shuffled)) == expected


# GitHub CLI calls


def test_fetchCommand():
    r"""!The list command asks for all pages of the repository"""
    gh = FakeGh([])
    prune_runs.fetch_runs("owner/repo", gh)
    assert gh.calls == [["gh", "api", "--paginate", "repos/owner/repo/actions/runs?per_page=100", "--jq", prune_runs.LIST_JQ]]


def test_fetchFailingCli():
    r"""!A failing CLI is reported with its message"""
    with pytest.raises(RuntimeError, match="Could not read the runs: HTTP 403"):
        prune_runs.fetch_runs("o/r", FakeGh([], listFailure="HTTP 403: Resource not accessible by integration"))


@pytest.mark.parametrize("bad", ["no json\n", '{"id": 1}\nbroken\n', "[1, 2]\n", '{"no_id": 5}\n'])
def test_fetchGarbageRefused(bad):
    r"""!Garbage from GitHub is refused"""
    with pytest.raises(RuntimeError, match="Unexpected response from GitHub in line"):
        prune_runs.fetch_runs("o/r", lambda *a, **k: subprocess.CompletedProcess([], 0, bad, ""))


def test_fetchMissingCli():
    r"""!A missing gh is reported clearly"""
    def runner(*a, **k):
        raise FileNotFoundError("gh")
    with pytest.raises(RuntimeError, match=r"GitHub CLI \(gh\) not found"):
        prune_runs.fetch_runs("o/r", runner)


def test_deleteCommandAndFailure():
    r"""!Delete exactly this run, return the reason on failure"""
    gh = FakeGh([], failIds=[2])
    assert prune_runs.delete_run("owner/repo", 4711, gh) == (True, "")
    assert gh.calls[-1] == ["gh", "api", "-X", "DELETE", "repos/owner/repo/actions/runs/4711"]
    assert prune_runs.delete_run("o/r", 2, gh) == (False, "HTTP 403: Forbidden")
    assert prune_runs.delete_run("o/r", 1, lambda c, **k: subprocess.CompletedProcess(c, 7, "", "")) == (False, "return code 7")


# main


def test_mainDryRun(runMain, summaryFile, capsys):
    r"""!A dry run deletes nothing but shows what would go"""
    gh = FakeGh(makeRuns(15, 31))
    code, sleeps = runMain(gh, "--dry-run")
    out = capsys.readouterr().out
    assert (code, gh.deleted, sleeps) == (0, [], [])
    assert all("DELETE" not in call for call in gh.calls)
    assert "Dry run (nothing is deleted): 15 runs found, 5 of them may be deleted" in out
    assert out.count("would delete:") == 5
    assert "Dry run: 5 would be deleted, nothing was deleted" in summaryFile.read_text(encoding="utf-8")


def test_mainRealRun(runMain, summaryFile):
    r"""!A real run deletes the selected runs oldest first and pauses after each one"""
    gh = FakeGh(makeRuns(15, 31))
    code, sleeps = runMain(gh)
    assert (code, gh.deleted, sleeps) == (0, [15, 14, 13, 12, 11], [0.1] * 5)
    assert "- Deleted: 5" in summaryFile.read_text(encoding="utf-8")


def test_mainOneFailureDoesNotStopOthers(runMain, summaryFile, capsys):
    r"""!One failure does not stop the others but makes the job fail"""
    gh = FakeGh(makeRuns(15, 31), failIds=[13])
    code, _ = runMain(gh)
    assert (code, gh.deleted) == (1, [15, 14, 12, 11])
    assert "HTTP 403: Forbidden" in capsys.readouterr().err
    assert "- Not deleted (errors): 1" in summaryFile.read_text(encoding="utf-8")


def test_mainLimitAndRest(runMain, capsys):
    r"""!The limit is respected and the rest is announced"""
    gh = FakeGh(makeRuns(15, 31))
    assert runMain(gh, "--max-deletions", "2")[0] == 0
    assert gh.deleted == [15, 14]
    assert "3 run(s) left for the next call (limit: 2 per call)" in capsys.readouterr().out


def test_mainThresholds(runMain):
    r"""!Default is 30 days and the newest 10, both can be changed"""
    gh = FakeGh(makeRuns(10, 1) + [makeRun(100, 29), makeRun(101, 31)])
    runMain(gh)
    assert gh.deleted == [101]
    gh = FakeGh(makeRuns(8, 5))
    runMain(gh, "--keep-days", "3", "--keep-per-workflow", "5")
    assert gh.deleted == [8, 7, 6]


def test_mainCurrentRunFromEnvironment(runMain, monkeypatch):
    r"""!The running job is excluded via GITHUB_RUN_ID, the argument wins"""
    monkeypatch.setenv("GITHUB_RUN_ID", "15")
    gh = FakeGh(makeRuns(15, 31))
    runMain(gh)
    assert gh.deleted == [14, 13, 12, 11]
    gh = FakeGh(makeRuns(15, 31))
    runMain(gh, "--current-run-id", "14")
    assert gh.deleted == [15, 13, 12, 11]


def test_mainReadErrorDeletesNothing(runMain, capsys):
    r"""!A read error stops everything without deleting anything"""
    gh = FakeGh(makeRuns(15, 31), listFailure="HTTP 401: Bad credentials")
    assert runMain(gh)[0] == 2
    assert gh.deleted == []
    assert "Error: Could not read the runs: HTTP 401" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["--keep-days", "-1"], ["--keep-per-workflow", "-1"], ["--max-deletions", "-5"]])
def test_mainNegativeValuesRefused(runMain, args):
    r"""!Negative values are refused"""
    with pytest.raises(SystemExit) as caught:
        runMain(FakeGh([]), *args)
    assert caught.value.code == 2


def test_mainWithoutSummaryFile(runMain, monkeypatch):
    r"""!Without a summary file nothing breaks"""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    assert runMain(FakeGh(makeRuns(15, 31)), "--dry-run")[0] == 0


FAKE_GH = """#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if "--paginate" in args:
    sys.stdout.write(open(os.environ["FAKE_GH_RUNS"], encoding="utf-8").read())
    sys.exit(0)
if args[:3] == ["api", "-X", "DELETE"]:
    with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
        log.write(args[3].rsplit("/", 1)[1] + "\\n")
    sys.exit(0)
sys.exit(9)
"""


def test_scriptAsRealProcess(tmp_path, monkeypatch):
    r"""!Start the script like the workflow does, with a fake gh as real program"""
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    runsFile = tmp_path / "runs.jsonl"
    runsFile.write_text("\n".join(json.dumps(r) for r in makeRuns(15, 400)) + "\n", encoding="utf-8")
    log = tmp_path / "deleted.txt"
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"], FAKE_GH_RUNS=str(runsFile),
               FAKE_GH_LOG=str(log), GITHUB_STEP_SUMMARY="", GITHUB_RUN_ID="")

    result = subprocess.run([sys.executable, SCRIPT, "--repo", "o/r", "--dry-run"], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "would delete:" in result.stdout
    assert not log.exists()

    result = subprocess.run([sys.executable, SCRIPT, "--repo", "o/r"], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert sorted(int(x) for x in log.read_text(encoding="utf-8").split()) == [11, 12, 13, 14, 15]
