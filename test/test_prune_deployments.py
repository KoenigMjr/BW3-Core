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

@file:        test_prune_deployments.py
@date:        12.10.2026
@author:      KoenigMjr
@description: Unittests for BOSWatch. File have to run as "pytest" unittest

The script deletes, so these tests mainly pin down the protection rules: the newest deployments and the live one
always stay, never a queued, pending or running one, never an unknown state and never one without a readable date.
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

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "scripts", "prune_deployments.py")
spec = importlib.util.spec_from_file_location("prune_deployments", SCRIPT)
prune_deployments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prune_deployments)

NOW = dt.datetime(2026, 10, 12, 12, 0, 0, tzinfo=dt.timezone.utc)


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


def makeDeployment(depId, daysOld):
    r"""!A deployment that was created daysOld days ago"""
    created = NOW - dt.timedelta(days=daysOld)
    return {"id": depId, "environment": "github-pages", "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha": f"{depId:040x}"}


def makeDeployments(count, firstId=1):
    r"""!count deployments, id 1 is the newest, higher ids are older"""
    return [makeDeployment(firstId + i, i) for i in range(count)]


def ids(selected):
    return [deployment["id"] for deployment, _ in selected]


def select(deployments, states=None, keepLast=5, limit=None, default="inactive"):
    r"""!Select with a fixed state per id (default: inactive)"""
    states = states or {}
    return prune_deployments.select_deployments_to_delete(
        deployments, keepLast, lambda d: states.get(d["id"], default), limit)


class FakeGh:
    r"""!Replaces subprocess.run: list, statuses, set inactive, delete"""

    def __init__(self, deployments, states=None, failDelete=(), failInactive=(), listFailure=None, statusFailure=None):
        self.deployments = deployments
        self.states = dict(states or {})
        self.failDelete = set(failDelete)
        self.failInactive = set(failInactive)
        self.listFailure = listFailure
        self.statusFailure = statusFailure
        self.deleted = []
        self.inactivated = []
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if "--paginate" in cmd:
            if self.listFailure:
                return subprocess.CompletedProcess(cmd, 1, "", self.listFailure)
            return subprocess.CompletedProcess(cmd, 0, "".join(json.dumps(d) + "\n" for d in self.deployments), "")
        if "POST" in cmd:
            depId = int(cmd[4].split("/")[4])
            if depId in self.failInactive:
                return subprocess.CompletedProcess(cmd, 1, "", "HTTP 403: Forbidden")
            self.inactivated.append(depId)
            self.states[depId] = "inactive"
            return subprocess.CompletedProcess(cmd, 0, "{}", "")
        if "DELETE" in cmd:
            depId = int(cmd[-1].rsplit("/", 1)[1])
            if depId in self.failDelete:
                return subprocess.CompletedProcess(cmd, 1, "", "HTTP 422: We cannot delete an active deployment")
            self.deleted.append(depId)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if self.statusFailure:
            return subprocess.CompletedProcess(cmd, 1, "", self.statusFailure)
        depId = int(cmd[2].split("/")[4])
        state = self.states.get(depId, "inactive")
        return subprocess.CompletedProcess(cmd, 0, json.dumps([{"state": state}] if state else []), "")

    def writes(self):
        return [call for call in self.calls if "POST" in call or "DELETE" in call]


@pytest.fixture()
def summaryFile(tmp_path, monkeypatch):
    r"""!Provide a step summary file"""
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    return path


@pytest.fixture()
def runMain(summaryFile):
    r"""!Run main() with a fake gh, returns (return code, sleeps)"""
    def _run(gh, *args):
        sleeps = []
        code = prune_deployments.main(["--repo", "o/r", *args], runner=gh, sleep=sleeps.append)
        return code, sleeps
    return _run


# selection


def test_selectOlderThanNewestOldestFirst():
    r"""!Everything beyond the newest n is selected, oldest first"""
    selected, unchecked = select(makeDeployments(8), {1: "success"})
    assert (ids(selected), unchecked) == ([8, 7, 6], 0)


def test_selectNothingWhenFewEnough():
    r"""!With n or fewer deployments nothing is selected"""
    assert select(makeDeployments(5))[0] == []
    assert select(makeDeployments(3), keepLast=10)[0] == []


def test_selectNeverLiveDeployment():
    r"""!The newest successful deployment stays even if it is old (newer ones failed)"""
    states = {i: "failure" for i in range(1, 6)}
    states[7] = "success"
    states[9] = "success"
    selected, _ = select(makeDeployments(10), states)
    assert ids(selected) == [10, 9, 8, 6]                                     # 7 is live, 9 is an older success


def test_selectWithoutAnySuccess():
    r"""!Without any successful deployment the old ones still go"""
    assert ids(select(makeDeployments(7), default="failure")[0]) == [7, 6]


@pytest.mark.parametrize("state", ["queued", "pending", "in_progress", "waiting", "something_new"])
def test_selectNeverUnfinishedOrUnknown(state):
    r"""!Queued, pending, running and unknown states are never selected"""
    assert select(makeDeployments(6), {6: state})[0] == []


@pytest.mark.parametrize("state", [None, "inactive", "success", "failure", "error"])
def test_selectFinishedStates(state):
    r"""!Finished states and deployments without status may go (if not live)"""
    selected, _ = select(makeDeployments(6), {1: "success", 6: state})
    assert selected == [(makeDeployments(6)[5], state)]


def test_selectNeverWithoutReadableDate():
    r"""!Deployments without a readable date always stay and do not use a slot"""
    broken = [dict(makeDeployment(100 + i, 50), created_at=value) for i, value in enumerate([None, "broken", 12345])]
    assert ids(select(broken + makeDeployments(6))[0]) == [6]


def test_selectLimit():
    r"""!The limit takes the oldest first and reports the unchecked rest"""
    selected, unchecked = select(makeDeployments(15), limit=3)
    assert (ids(selected), unchecked) == ([15, 14, 13], 7)
    assert select(makeDeployments(15), limit=0) == ([], 10)
    assert select(makeDeployments(15), limit=100)[1] == 0


def test_selectLimitCountsOnlySelected():
    r"""!Skipped deployments do not use up the limit"""
    selected, unchecked = select(makeDeployments(10), {10: "in_progress", 9: "queued"}, limit=2)
    assert (ids(selected), unchecked) == ([8, 7], 1)


def test_selectStatesAreFetchedOnce():
    r"""!Every state is fetched at most once"""
    asked = []
    prune_deployments.select_deployments_to_delete(makeDeployments(10), 5, lambda d: asked.append(d["id"]) or "inactive")
    assert sorted(asked) == list(range(1, 11))


def test_selectOrderOfInputIrrelevant():
    r"""!The order of the input does not matter"""
    deployments = makeDeployments(12)
    expected = ids(select(deployments, {3: "success"})[0])
    for seed in range(5):
        shuffled = list(deployments)
        random.Random(seed).shuffle(shuffled)
        assert ids(select(shuffled, {3: "success"})[0]) == expected


# GitHub CLI calls


def test_fetchCommands():
    r"""!List all pages of the environment, status asks only for the newest entry"""
    gh = FakeGh(makeDeployments(2), {1: "success"})
    assert [d["id"] for d in prune_deployments.fetch_deployments("owner/repo", "github-pages", gh)] == [1, 2]
    assert gh.calls[0] == ["gh", "api", "--paginate", "repos/owner/repo/deployments?environment=github-pages&per_page=100",
                           "--jq", prune_deployments.LIST_JQ]
    assert prune_deployments.fetch_state("owner/repo", 1, gh) == "success"
    assert gh.calls[1] == ["gh", "api", "repos/owner/repo/deployments/1/statuses?per_page=1"]


def test_fetchStateWithoutStatus():
    r"""!A deployment without any status has the state None"""
    assert prune_deployments.fetch_state("o/r", 1, FakeGh([], {1: None})) is None


@pytest.mark.parametrize("bad", ["no json", '{"state": "x"}'])
def test_fetchStateGarbageRefused(bad):
    r"""!Garbage in a status response is refused"""
    with pytest.raises(RuntimeError, match="Unexpected status response"):
        prune_deployments.fetch_state("o/r", 1, lambda *a, **k: subprocess.CompletedProcess([], 0, bad, ""))


@pytest.mark.parametrize("bad", ["no json\n", "[1, 2]\n", '{"no_id": 5}\n'])
def test_fetchDeploymentsGarbageRefused(bad):
    r"""!Garbage in the list is refused"""
    with pytest.raises(RuntimeError, match="Unexpected response from GitHub in line"):
        prune_deployments.fetch_deployments("o/r", "github-pages", lambda *a, **k: subprocess.CompletedProcess([], 0, bad, ""))


def test_fetchMissingCli():
    r"""!A missing gh is reported clearly"""
    def runner(*a, **k):
        raise FileNotFoundError("gh")
    with pytest.raises(RuntimeError, match=r"GitHub CLI \(gh\) not found"):
        prune_deployments.fetch_deployments("o/r", "github-pages", runner)


def test_deleteSetsInactiveFirst():
    r"""!A deployment that is not inactive is marked inactive, then deleted"""
    gh = FakeGh([])
    assert prune_deployments.delete_deployment("owner/repo", 7, "failure", gh) == (True, "")
    assert gh.calls == [["gh", "api", "-X", "POST", "repos/owner/repo/deployments/7/statuses", "-f", "state=inactive"],
                        ["gh", "api", "-X", "DELETE", "repos/owner/repo/deployments/7"]]


def test_deleteInactiveDirectly():
    r"""!An inactive deployment is deleted without a new status"""
    gh = FakeGh([])
    assert prune_deployments.delete_deployment("o/r", 7, "inactive", gh) == (True, "")
    assert gh.inactivated == [] and gh.deleted == [7]


def test_deleteNotWhenInactiveFails():
    r"""!If marking inactive fails, nothing is deleted"""
    gh = FakeGh([], failInactive=[7])
    assert prune_deployments.delete_deployment("o/r", 7, "success", gh) == (False, "set inactive: HTTP 403: Forbidden")
    assert gh.deleted == []


# main


def test_mainDryRunChangesNothing(runMain, summaryFile, capsys):
    r"""!A dry run reads, but never writes"""
    gh = FakeGh(makeDeployments(8), {1: "success", 7: "failure"})
    code, sleeps = runMain(gh, "--dry-run")
    out = capsys.readouterr().out
    assert (code, gh.writes(), sleeps) == (0, [], [])
    assert "8 deployments of 'github-pages' found, 3 of them selected" in out
    assert out.count("would delete:") == 3
    assert "Dry run: 3 would be deleted, nothing was changed" in summaryFile.read_text(encoding="utf-8")


def test_mainRealRun(runMain, summaryFile):
    r"""!A real run deletes oldest first, only non-inactive ones get a new status"""
    gh = FakeGh(makeDeployments(8), {1: "success", 7: "failure"})
    code, sleeps = runMain(gh)
    assert (code, gh.deleted, gh.inactivated, sleeps) == (0, [8, 7, 6], [7], [0.1] * 3)
    assert "- Deleted: 3" in summaryFile.read_text(encoding="utf-8")


def test_mainDefaultKeepsFive(runMain):
    r"""!Default is to keep the newest 5"""
    gh = FakeGh(makeDeployments(7), {1: "success"})
    runMain(gh)
    assert gh.deleted == [7, 6]


def test_mainKeepLast(runMain):
    r"""!keep-last can be changed, but must be at least 1"""
    gh = FakeGh(makeDeployments(12), {1: "success"})
    runMain(gh, "--keep-last", "10")
    assert gh.deleted == [12, 11]
    with pytest.raises(SystemExit) as caught:
        runMain(FakeGh([]), "--keep-last", "0")
    assert caught.value.code == 2


def test_mainOneFailureDoesNotStopOthers(runMain, summaryFile, capsys):
    r"""!One failure does not stop the others but makes the job fail"""
    gh = FakeGh(makeDeployments(8), {1: "success"}, failDelete=[7])
    code, _ = runMain(gh)
    assert (code, gh.deleted) == (1, [8, 6])
    assert "HTTP 422" in capsys.readouterr().err
    assert "- Not deleted (errors): 1" in summaryFile.read_text(encoding="utf-8")


def test_mainLimitAndRest(runMain, capsys):
    r"""!The limit is respected and the rest is announced"""
    gh = FakeGh(makeDeployments(10), {1: "success"})
    assert runMain(gh, "--max-deletions", "2")[0] == 0
    assert gh.deleted == [10, 9]
    assert "3 older deployment(s) not checked (limit: 2 per call)" in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["listFailure", "statusFailure"])
def test_mainReadErrorChangesNothing(runMain, capsys, failure):
    r"""!A read error (list or status) stops everything before anything is changed"""
    gh = FakeGh(makeDeployments(8), **{failure: "HTTP 401: Bad credentials"})
    assert runMain(gh)[0] == 2
    assert gh.writes() == []
    assert "HTTP 401" in capsys.readouterr().err


def test_mainNegativeLimitRefused(runMain):
    r"""!A negative limit is refused"""
    with pytest.raises(SystemExit) as caught:
        runMain(FakeGh([]), "--max-deletions", "-1")
    assert caught.value.code == 2


FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[2:]
if "--paginate" in args:
    sys.stdout.write(open(os.environ["FAKE_GH_DEPLOYMENTS"], encoding="utf-8").read())
elif args[:2] == ["-X", "DELETE"] or args[:2] == ["-X", "POST"]:
    with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
        log.write(args[1] + " " + args[2].split("/")[4] + "\\n")
else:
    sys.stdout.write(json.dumps([{"state": "success" if args[0].split("/")[4] == "1" else "failure"}]))
"""


def test_scriptAsRealProcess(tmp_path):
    r"""!Start the script like the workflow does, with a fake gh as real program"""
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    deploymentsFile = tmp_path / "deployments.jsonl"
    deploymentsFile.write_text("".join(json.dumps(d) + "\n" for d in makeDeployments(7)), encoding="utf-8")
    log = tmp_path / "writes.txt"
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"], FAKE_GH_DEPLOYMENTS=str(deploymentsFile),
               FAKE_GH_LOG=str(log), GITHUB_STEP_SUMMARY="")

    result = subprocess.run([sys.executable, SCRIPT, "--repo", "o/r", "--dry-run"], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("would delete:") == 2
    assert not log.exists()

    result = subprocess.run([sys.executable, SCRIPT, "--repo", "o/r"], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").split("\n")[:-1] == ["POST 7", "DELETE 7", "POST 6", "DELETE 6"]
