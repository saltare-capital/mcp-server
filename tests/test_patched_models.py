#!/usr/bin/env python3
"""Local Pydantic validation tests for Saltare-patched fields.

Runs against system pydantic (currently 2.13.4). Patches target stable
Pydantic v2 APIs unchanged between 2.11 (Docker image) and 2.13 (droplet
system Python). The B3 Docker build provides the production-environment
fidelity check; this script provides fast feedback at the Pydantic layer
only.

Usage: python3 tests/test_patched_models.py
"""
import sys
from pathlib import Path

# Mirror the pyproject pytest pythonpath = "src tests" setup so plain
# python3 invocation resolves the model imports the same way pytest does.
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from pydantic import ValidationError
from models import (
    LiveForm,
    ProjectFile,
    BacktestSummaryResult,
    LeanVersion,
    Project,
    ProjectListResponse,
    NotifyInsights,
    NotifyOrderEvents,
    AutoRestart,
)

results = []


def test(name, fn):
    try:
        fn()
        results.append((True, name, None))
        print(f"PASS: {name}")
    except AssertionError as e:
        results.append((False, name, f"assertion: {e}"))
        print(f"FAIL: {name}: assertion: {e}")
    except ValidationError as e:
        results.append((False, name, f"unexpected ValidationError: {e}"))
        print(f"FAIL: {name}: unexpected ValidationError: {e}")
    except Exception as e:
        results.append((False, name, f"unexpected {type(e).__name__}: {e}"))
        print(f"FAIL: {name}: unexpected {type(e).__name__}: {e}")


# --- Test 1: LiveForm accepts Python bool (the Stage-1 fix) ---
def test_liveform_accepts_python_bool():
    lf = LiveForm.model_validate({
        'notifyInsights': True,
        'notifyOrderEvents': False,
        'autoRestart': True,
    })
    assert lf.notifyInsights == NotifyInsights.true, f"got {lf.notifyInsights!r}"
    assert lf.notifyOrderEvents == NotifyOrderEvents.false, f"got {lf.notifyOrderEvents!r}"
    assert lf.autoRestart == AutoRestart.true, f"got {lf.autoRestart!r}"


# --- Test 2: LiveForm still accepts string-enum input (backwards compat) ---
def test_liveform_still_accepts_strings():
    lf = LiveForm.model_validate({
        'notifyInsights': 'true',
        'notifyOrderEvents': 'false',
        'autoRestart': 'true',
    })
    assert lf.notifyInsights == NotifyInsights.true
    assert lf.notifyOrderEvents == NotifyOrderEvents.false
    assert lf.autoRestart == AutoRestart.true


# --- Test 3: LiveForm mixed bool/str input ---
def test_liveform_mixed_input():
    lf = LiveForm.model_validate({
        'notifyInsights': True,           # bool
        'notifyOrderEvents': 'false',     # str
        'autoRestart': False,             # bool
    })
    assert lf.notifyInsights == NotifyInsights.true
    assert lf.notifyOrderEvents == NotifyOrderEvents.false
    assert lf.autoRestart == AutoRestart.false


# --- Test 4: ProjectFile.modified accepts arbitrary strings ---
def test_projectfile_modified_accepts_arbitrary_string():
    for value in (
        '2025-09-09T01:23:45',          # naive ISO, no TZ
        '2025-09-09T01:23:45Z',         # UTC Zulu
        '2025-09-09T01:23:45+00:00',    # explicit UTC offset
        'some-non-iso-string',          # garbage string, still str-typed
        '2025-09-09 01:23:45',          # space separator
        '09/09/2025',                   # US date format
    ):
        pf = ProjectFile.model_validate({'modified': value})
        assert pf.modified == value, f"roundtrip mismatch for {value!r}: got {pf.modified!r}"


# --- Test 5: ProjectFile.modified accepts None ---
def test_projectfile_modified_accepts_none():
    pf = ProjectFile.model_validate({'modified': None})
    assert pf.modified is None


# --- Test 6: BacktestSummaryResult.created str pass-through ---
def test_backtestsummaryresult_created_str_passthrough():
    for value in (
        '2025-09-09T01:23:45',
        '2025-09-09T01:23:45Z',
        'arbitrary-string',
        None,
    ):
        bsr = BacktestSummaryResult.model_validate({'created': value})
        assert bsr.created == value, f"mismatch for {value!r}: got {bsr.created!r}"


# --- Test 7: LeanVersion.created str pass-through ---
def test_leanversion_created_str_passthrough():
    for value in (
        '2025-09-09T01:23:45',
        '2025-09-09T01:23:45Z',
        'arbitrary-string',
        None,
    ):
        lv = LeanVersion.model_validate({'created': value})
        assert lv.created == value, f"mismatch for {value!r}: got {lv.created!r}"


# --- Test 8a: Project.modified and Project.created accept str (required) ---
def test_project_required_str_dates_accept_string():
    p = Project.model_validate({
        'projectId': 31546731,
        'organizationId': '5cad178b20a1d52567b534553413b691',
        'name': 'TestProject',
        'modified': '2025-09-09T01:23:45',
        'created': '2025-09-09T01:23:45',
        'ownerId': 365490,
        'language': 'Py',
    })
    assert p.modified == '2025-09-09T01:23:45'
    assert p.created == '2025-09-09T01:23:45'


# --- Test 8b: Project.modified rejects None (non-Optional preserved) ---
def test_project_modified_rejects_None():
    base = {
        'projectId': 31546731,
        'organizationId': '5cad178b20a1d52567b534553413b691',
        'name': 'TestProject',
        'modified': None,                          # bad input
        'created': '2025-09-09T01:23:45',
        'ownerId': 365490,
        'language': 'Py',
    }
    try:
        Project.model_validate(base)
    except ValidationError:
        return  # expected
    raise AssertionError("Project.modified=None did NOT raise ValidationError; non-Optional contract lost")


# --- Test 8c: Project.created rejects None (non-Optional preserved) ---
def test_project_created_rejects_None():
    base = {
        'projectId': 31546731,
        'organizationId': '5cad178b20a1d52567b534553413b691',
        'name': 'TestProject',
        'modified': '2025-09-09T01:23:45',
        'created': None,                           # bad input
        'ownerId': 365490,
        'language': 'Py',
    }
    try:
        Project.model_validate(base)
    except ValidationError:
        return  # expected
    raise AssertionError("Project.created=None did NOT raise ValidationError; non-Optional contract lost")


# --- Test 9: Full synthetic ProjectListResponse integration test ---
def test_full_projectlist_response_synthetic():
    """Reproduce the Phase 2 failure shape: list_projects response with
    one liveForm-populated project (bool enum fields) and one with
    arbitrary-format datetime strings on Project.modified/created. Also
    a LeanVersion in the versions list with an arbitrary string created."""
    response = {
        'projects': [
            # Project with liveForm bool fields — the Phase 2 Stage-1 failure
            {
                'projectId': 199,
                'organizationId': '5cad178b20a1d52567b534553413b691',
                'name': 'SaltareLive199',
                'modified': '2024-12-01 14:23:45',
                'created': '2023-08-15 09:00:00',
                'ownerId': 365490,
                'language': 'Py',
                'liveForm': {
                    'notifyInsights': False,
                    'notifyOrderEvents': False,
                    'autoRestart': True,
                },
                'lastLiveDeployment': '2024-12-01T14:23:45',  # Optional[datetime] — sibling, not patched
            },
            # Project with arbitrary-format datetime strings on patched fields
            {
                'projectId': 31546731,
                'organizationId': '5cad178b20a1d52567b534553413b691',
                'name': 'TestProject',
                'modified': '09/09/2025 01:23:45 PM',  # non-ISO format
                'created': 'some-arbitrary-string',
                'ownerId': 365490,
                'language': 'Py',
            },
        ],
        'versions': [
            {
                'id': 12345,
                'created': '2024-08-22 12:00:00',  # arbitrary string format
                'description': 'LEAN 16500',
            },
        ],
        'success': True,
    }
    plr = ProjectListResponse.model_validate(response)
    assert plr.success is True
    assert plr.projects is not None and len(plr.projects) == 2
    # First project: liveForm bool coercion check
    p0 = plr.projects[0]
    assert p0.liveForm is not None
    assert p0.liveForm.notifyInsights == NotifyInsights.false
    assert p0.liveForm.notifyOrderEvents == NotifyOrderEvents.false
    assert p0.liveForm.autoRestart == AutoRestart.true
    # Second project: patched str fields pass through verbatim
    p1 = plr.projects[1]
    assert p1.modified == '09/09/2025 01:23:45 PM'
    assert p1.created == 'some-arbitrary-string'
    # LeanVersion: patched str field passes through verbatim
    assert plr.versions is not None and len(plr.versions) == 1
    assert plr.versions[0].created == '2024-08-22 12:00:00'


# --- Run all tests ---
tests = [
    ('test_liveform_accepts_python_bool',           test_liveform_accepts_python_bool),
    ('test_liveform_still_accepts_strings',          test_liveform_still_accepts_strings),
    ('test_liveform_mixed_input',                    test_liveform_mixed_input),
    ('test_projectfile_modified_accepts_arbitrary_string', test_projectfile_modified_accepts_arbitrary_string),
    ('test_projectfile_modified_accepts_none',       test_projectfile_modified_accepts_none),
    ('test_backtestsummaryresult_created_str_passthrough', test_backtestsummaryresult_created_str_passthrough),
    ('test_leanversion_created_str_passthrough',     test_leanversion_created_str_passthrough),
    ('test_project_required_str_dates_accept_string', test_project_required_str_dates_accept_string),
    ('test_project_modified_rejects_None',           test_project_modified_rejects_None),
    ('test_project_created_rejects_None',            test_project_created_rejects_None),
    ('test_full_projectlist_response_synthetic',     test_full_projectlist_response_synthetic),
]

for name, fn in tests:
    test(name, fn)

failed = [r for r in results if not r[0]]
print(f"\n{'=' * 60}")
print(f"{len(results)} tests, {len(failed)} failed")
sys.exit(1 if failed else 0)
