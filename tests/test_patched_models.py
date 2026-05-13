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
from datetime import datetime as _dt_obj
from models import (
    LiveForm,
    ProjectFile,
    BacktestResult,
    BacktestSummaryResult,
    OptimizationBacktest,
    LeanVersion,
    Project,
    ProjectListResponse,
    NotifyInsights,
    NotifyOrderEvents,
    AutoRestart,
    # Patch 4 additions
    ObjectStoreProperties,
    ObjectStoreSummary,
    LiveAlgorithmSummary,
    LiveAlgorithm,
    LiveAlgorithmResults,
    Trade,
    TradeStatistics,
    Version,
    CreateOptimizationResponse,
    Order,
    Optimization,
)

# Realistic parameter-dict shapes derived from the B5.1 ValidationError input_value
# examples (e.g., {'key': 'history_lookback', 'min': 0, 'max': 0, 'step': 0}).
SAMPLE_PARAMETER_DICTS = [
    {'key': 'history_lookback', 'min': 5, 'max': 30, 'step': 1},
    {'key': 'rebalance_period', 'min': 1.0, 'max': 90.0, 'step': 1.0},
    {'key': 'threshold', 'min': 0.01, 'max': 0.5, 'step': 0.01},
]

# ============================================================================
# Stage-2 methodology upgrade (Patch 4 additions)
# ============================================================================
#
# WHY THESE TESTS EXIST
# ---------------------
# B-iter.5 surfaced a Stage-2 failure (FastMCP outputSchema MCP -32602) on
# Project.lastLiveDeployment after Patches 1-3 cleared Stage 1 entirely. The
# B2 suite at that point tested Stage 1 (Pydantic model_validate) only.
# Stage 2 (JSON Schema 'format: date-time' on serialized output) was untested
# locally, so the failure only surfaced at integration time. The specific
# trigger format was '+0000' offset (no colon), which Pydantic 2.13.4
# accepts via lenient datetime parsing but JSON Schema rejects via RFC 3339
# format check.
#
# WHAT THESE TESTS DO
# -------------------
# For each of the 31 Patch-4 fields (Optional[datetime] -> Optional[str]),
# verify the patched type accepts the 8 date-time format variations QC's API
# may emit, including the '+0000' offset that triggered B-iter.5. None
# should raise ValidationError on model_validate.
#
# WHAT THESE TESTS DON'T DO
# -------------------------
# These tests do not run the FastMCP outputSchema validator. That requires
# the MCP server runtime (Phase 5 work). These tests verify the upstream
# invariant: the patched field is permissive enough that Stage 1 cannot
# reject any string the API emits. Stage 2 verification still requires the
# integration discriminator at B-iter2.6.
#
# METHODOLOGICAL LIMITATION
# -------------------------
# A passing test here does NOT guarantee Stage 2 will pass. Patch 4's
# premise is that FastMCP derives outputSchema from the Pydantic model
# declaration, so Optional[str] yields a JSON Schema with no
# 'format: date-time' constraint. If FastMCP's tool definitions hard-code
# the schema independently of the model, Patch 4 won't propagate. That
# unknown is what B-iter2.6 will discriminate.
# ============================================================================

DATETIME_FORMAT_VARIATIONS = [
    '2025-09-09T01:23:45',           # naive ISO, no TZ
    '2025-09-09T01:23:45Z',          # UTC Zulu
    '2025-09-09T01:23:45+00:00',     # RFC 3339 with colon offset
    '2025-09-09T01:23:45+0000',      # B-iter.5 trigger: offset without colon
    '2025-09-09 01:23:45',           # space separator
    '09/09/2025',                    # US date format
    'arbitrary-string',              # negative-format soak: non-date string
    None,                            # Optional invariant preservation
]

# Required-fields bases for the two patched classes with non-Optional fields.
PROJECT_REQUIRED_BASE = {
    'projectId': 31546731,
    'organizationId': '5cad178b20a1d52567b534553413b691',
    'name': 'Patch4-format-variation-test',
    'modified': '2025-09-09T01:23:45',
    'created': '2025-09-09T01:23:45',
    'ownerId': 365490,
    'language': 'Py',
}
OPTIMIZATION_REQUIRED_BASE = {'projectId': 31546731}


def _validate_field_variations(cls, fields, base=None):
    """For each (field, variation) pair, instantiate cls with that field
    populated and assert round-trip equality. Optional `base` provides any
    required fields the class needs (only Project has these)."""
    base = base or {}
    for fld in fields:
        for variation in DATETIME_FORMAT_VARIATIONS:
            data = {**base, fld: variation}
            obj = cls.model_validate(data)
            actual = getattr(obj, fld)
            assert actual == variation, (
                f"{cls.__name__}.{fld} round-trip mismatch for {variation!r}: "
                f"got {actual!r}"
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


# --- Test 10: Project.parameters accepts list-of-dicts (Patch 3) ---
def test_project_parameters_accepts_list_of_dicts():
    base = {
        'projectId': 31546731,
        'organizationId': '5cad178b20a1d52567b534553413b691',
        'name': 'TestProject',
        'modified': '2025-09-09T01:23:45',
        'created': '2025-09-09T01:23:45',
        'ownerId': 365490,
        'language': 'Py',
        'parameters': SAMPLE_PARAMETER_DICTS,
    }
    p = Project.model_validate(base)
    assert p.parameters == SAMPLE_PARAMETER_DICTS
    assert len(p.parameters) == 3


# --- Test 11: Project.parameters accepts empty list ---
def test_project_parameters_accepts_empty_list():
    base = {
        'projectId': 31546731,
        'organizationId': '5cad178b20a1d52567b534553413b691',
        'name': 'TestProject',
        'modified': '2025-09-09T01:23:45',
        'created': '2025-09-09T01:23:45',
        'ownerId': 365490,
        'language': 'Py',
        'parameters': [],
    }
    p = Project.model_validate(base)
    assert p.parameters == []


# --- Test 12: Project.parameters accepts None ---
def test_project_parameters_accepts_None():
    base = {
        'projectId': 31546731,
        'organizationId': '5cad178b20a1d52567b534553413b691',
        'name': 'TestProject',
        'modified': '2025-09-09T01:23:45',
        'created': '2025-09-09T01:23:45',
        'ownerId': 365490,
        'language': 'Py',
        'parameters': None,
    }
    p = Project.model_validate(base)
    assert p.parameters is None


# --- Test 13: BacktestResult.parameterSet accepts list-of-dicts (Patch 3) ---
def test_backtestresult_parameterset_accepts_list_of_dicts():
    br = BacktestResult.model_validate({'parameterSet': SAMPLE_PARAMETER_DICTS})
    assert br.parameterSet == SAMPLE_PARAMETER_DICTS
    assert len(br.parameterSet) == 3


# --- Test 14: BacktestResult.parameterSet accepts empty list ---
def test_backtestresult_parameterset_accepts_empty_list():
    br = BacktestResult.model_validate({'parameterSet': []})
    assert br.parameterSet == []


# --- Test 15: BacktestResult.parameterSet accepts None ---
def test_backtestresult_parameterset_accepts_None():
    br = BacktestResult.model_validate({'parameterSet': None})
    assert br.parameterSet is None


# --- Test 16: BacktestSummaryResult.parameterSet accepts list-of-dicts (Patch 3) ---
def test_backtestsummaryresult_parameterset_accepts_list_of_dicts():
    bsr = BacktestSummaryResult.model_validate({'parameterSet': SAMPLE_PARAMETER_DICTS})
    assert bsr.parameterSet == SAMPLE_PARAMETER_DICTS
    assert len(bsr.parameterSet) == 3


# --- Test 17: BacktestSummaryResult.parameterSet accepts empty list ---
def test_backtestsummaryresult_parameterset_accepts_empty_list():
    bsr = BacktestSummaryResult.model_validate({'parameterSet': []})
    assert bsr.parameterSet == []


# --- Test 18: BacktestSummaryResult.parameterSet accepts None ---
def test_backtestsummaryresult_parameterset_accepts_None():
    bsr = BacktestSummaryResult.model_validate({'parameterSet': None})
    assert bsr.parameterSet is None


# --- Test 19: OptimizationBacktest.parameterSet accepts list-of-dicts (Patch 3) ---
def test_optimizationbacktest_parameterset_accepts_list_of_dicts():
    ob = OptimizationBacktest.model_validate({'parameterSet': SAMPLE_PARAMETER_DICTS})
    assert ob.parameterSet == SAMPLE_PARAMETER_DICTS
    assert len(ob.parameterSet) == 3


# --- Test 20: OptimizationBacktest.parameterSet accepts empty list ---
def test_optimizationbacktest_parameterset_accepts_empty_list():
    ob = OptimizationBacktest.model_validate({'parameterSet': []})
    assert ob.parameterSet == []


# --- Test 21: OptimizationBacktest.parameterSet accepts None ---
def test_optimizationbacktest_parameterset_accepts_None():
    ob = OptimizationBacktest.model_validate({'parameterSet': None})
    assert ob.parameterSet is None


# --- Test 22: Integration — BacktestSummaryResult with realistic parameterSet shape ---
def test_full_backtest_response_with_parameterset():
    """Mirror the B5.1 failure-shape for the parameterSet sibling: a realistic
    BacktestSummaryResult shape with parameterSet populated as list-of-dicts,
    sibling Patch-2 datetime field populated as arbitrary string. Validates the
    Stage-1 patch holds end-to-end for the model class targeted by list_backtests."""
    bsr = BacktestSummaryResult.model_validate({
        'backtestId': 'a1b2c3d4e5f6',
        'name': 'BacktestRun-2025-11-04',
        'note': 'parameter sweep run',
        'created': '2025-11-04 18:23:45',  # arbitrary str — covered by Patch 2
        'progress': 1.0,
        'parameterSet': SAMPLE_PARAMETER_DICTS,  # list-of-dicts — covered by Patch 3
        'tradeableDates': 252,
    })
    assert bsr.backtestId == 'a1b2c3d4e5f6'
    assert bsr.created == '2025-11-04 18:23:45'
    assert bsr.parameterSet == SAMPLE_PARAMETER_DICTS
    assert len(bsr.parameterSet) == 3


# --- Test 23: ObjectStoreProperties — Patch 4 format variations ---
def test_objectstoreproperties_format_variations():
    _validate_field_variations(ObjectStoreProperties, ('modified', 'created'))


# --- Test 24: LiveAlgorithmSummary — Patch 4 format variations ---
def test_liveaalgorithmsummary_format_variations():
    _validate_field_variations(LiveAlgorithmSummary, ('launched', 'stopped'))


# --- Test 25: ObjectStoreSummary — Patch 4 format variations ---
def test_objectstoresummary_format_variations():
    _validate_field_variations(ObjectStoreSummary, ('modified',))


# --- Test 26: Trade — Patch 4 format variations ---
def test_trade_format_variations():
    _validate_field_variations(Trade, ('entryTime', 'exitTime'))


# --- Test 27: TradeStatistics — Patch 4 format variations ---
def test_tradestatistics_format_variations():
    _validate_field_variations(TradeStatistics, ('startDateTime', 'endDateTime'))


# --- Test 28: Version — Patch 4 format variations (inline-decl edge case) ---
def test_version_format_variations():
    _validate_field_variations(Version, ('itimestamp',))


# --- Test 29: BacktestResult — Patch 4 format variations ---
def test_backtestresult_format_variations():
    _validate_field_variations(
        BacktestResult,
        ('backtestStart', 'backtestEnd', 'created', 'outOfSampleMaxEndDate'),
    )


# --- Test 30: CreateOptimizationResponse — Patch 4 format variations ---
def test_createoptimizationresponse_format_variations():
    _validate_field_variations(
        CreateOptimizationResponse,
        ('created', 'outOfSampleMaxEndDate'),
    )


# --- Test 31: LiveAlgorithm — Patch 4 format variations ---
def test_livealgorithm_format_variations():
    _validate_field_variations(LiveAlgorithm, ('launched', 'stopped'))


# --- Test 32: LiveAlgorithmResults — Patch 4 format variations ---
def test_livealgorithmresults_format_variations():
    _validate_field_variations(LiveAlgorithmResults, ('launched', 'stopped'))


# --- Test 33: OptimizationBacktest — Patch 4 format variations ---
def test_optimizationbacktest_format_variations():
    _validate_field_variations(
        OptimizationBacktest,
        ('startDate', 'endDate', 'outOfSampleMaxEndDate'),
    )


# --- Test 34: Order — Patch 4 format variations ---
def test_order_format_variations():
    _validate_field_variations(
        Order,
        ('time', 'createdTime', 'lastFillTime', 'lastUpdateTime', 'canceledTime'),
    )


# --- Test 35: Project.lastLiveDeployment — Patch 4 format variations ---
def test_project_lastlivedeployment_format_variations():
    _validate_field_variations(
        Project,
        ('lastLiveDeployment',),
        base=PROJECT_REQUIRED_BASE,
    )


# --- Test 36: Optimization — Patch 4 format variations ---
def test_optimization_format_variations():
    _validate_field_variations(
        Optimization,
        ('requested', 'outOfSampleMaxEndDate'),
        base=OPTIMIZATION_REQUIRED_BASE,
    )


# --- Test 37: datetime-object contract probe (Refinement 1) ---
def test_patched_field_datetime_object_contract():
    """Refinement 1 contract probe: what does Optional[str] do with a Python
    datetime object input under pydantic 2.13.4 default config? Either outcome
    (rejection or silent coercion) is informative for the audit trail."""
    dt_obj = _dt_obj(2025, 9, 9, 1, 23, 45)
    try:
        bsr = BacktestSummaryResult.model_validate({'created': dt_obj})
        assert isinstance(bsr.created, str), (
            f"silent-coercion result is not str: type={type(bsr.created).__name__}, "
            f"value={bsr.created!r}"
        )
        contract = 'coerce_to_str'
        contract_value = bsr.created
    except ValidationError:
        contract = 'reject'
        contract_value = None
    assert contract in ('coerce_to_str', 'reject'), f"unexpected contract: {contract}"
    print(f"  [contract observation] BacktestSummaryResult.created vs datetime "
          f"object: {contract}" + (f" -> {contract_value!r}" if contract_value else ''))


# --- Test 38: Cross-class soak — B-iter.5 failure-shape replication (Refinement 2) ---
def test_projectlist_response_b_iter5_failure_replication():
    """Cross-class soak: replicates the exact B-iter.5 failure wire-shape.
    Project.lastLiveDeployment with '+0000' format (no colon in offset) was
    the specific shape that triggered Stage-2 FastMCP outputSchema rejection
    on ~80 of Hugh's QC projects. Under Patch 4, Stage 1 must accept this
    format without ValidationError."""
    response = {
        'projects': [
            {
                'projectId': 199,
                'organizationId': '5cad178b20a1d52567b534553413b691',
                'name': 'B-iter5-replication-project-199',
                'modified': '2024-12-01 14:23:45',
                'created': '2023-08-15 09:00:00',
                'ownerId': 365490,
                'language': 'Py',
                'lastLiveDeployment': '2025-09-09T01:23:45+0000',  # THE failure format
            },
            {
                'projectId': 202,
                'organizationId': '5cad178b20a1d52567b534553413b691',
                'name': 'B-iter5-replication-project-202',
                'modified': '2024-11-15 09:00:00',
                'created': '2023-05-01 12:00:00',
                'ownerId': 365490,
                'language': 'Py',
                'lastLiveDeployment': None,  # null branch — Optional invariant
            },
            {
                'projectId': 217,
                'organizationId': '5cad178b20a1d52567b534553413b691',
                'name': 'B-iter5-replication-project-217',
                'modified': '2024-09-10 18:30:00',
                'created': '2023-04-22 14:15:30',
                'ownerId': 365490,
                'language': 'Py',
                'lastLiveDeployment': '2025-09-09T01:23:45',  # bare ISO, no TZ
            },
        ],
        'versions': [],
        'success': True,
    }
    plr = ProjectListResponse.model_validate(response)
    assert plr.success is True
    assert len(plr.projects) == 3
    assert plr.projects[0].lastLiveDeployment == '2025-09-09T01:23:45+0000'
    assert plr.projects[1].lastLiveDeployment is None
    assert plr.projects[2].lastLiveDeployment == '2025-09-09T01:23:45'


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
    ('test_project_parameters_accepts_list_of_dicts',     test_project_parameters_accepts_list_of_dicts),
    ('test_project_parameters_accepts_empty_list',         test_project_parameters_accepts_empty_list),
    ('test_project_parameters_accepts_None',                test_project_parameters_accepts_None),
    ('test_backtestresult_parameterset_accepts_list_of_dicts', test_backtestresult_parameterset_accepts_list_of_dicts),
    ('test_backtestresult_parameterset_accepts_empty_list',    test_backtestresult_parameterset_accepts_empty_list),
    ('test_backtestresult_parameterset_accepts_None',          test_backtestresult_parameterset_accepts_None),
    ('test_backtestsummaryresult_parameterset_accepts_list_of_dicts', test_backtestsummaryresult_parameterset_accepts_list_of_dicts),
    ('test_backtestsummaryresult_parameterset_accepts_empty_list',    test_backtestsummaryresult_parameterset_accepts_empty_list),
    ('test_backtestsummaryresult_parameterset_accepts_None',          test_backtestsummaryresult_parameterset_accepts_None),
    ('test_optimizationbacktest_parameterset_accepts_list_of_dicts', test_optimizationbacktest_parameterset_accepts_list_of_dicts),
    ('test_optimizationbacktest_parameterset_accepts_empty_list',    test_optimizationbacktest_parameterset_accepts_empty_list),
    ('test_optimizationbacktest_parameterset_accepts_None',          test_optimizationbacktest_parameterset_accepts_None),
    ('test_full_backtest_response_with_parameterset',                test_full_backtest_response_with_parameterset),
    # Patch 4: Stage-2 methodology upgrade — format variations across 14 classes
    ('test_objectstoreproperties_format_variations',     test_objectstoreproperties_format_variations),
    ('test_liveaalgorithmsummary_format_variations',     test_liveaalgorithmsummary_format_variations),
    ('test_objectstoresummary_format_variations',        test_objectstoresummary_format_variations),
    ('test_trade_format_variations',                     test_trade_format_variations),
    ('test_tradestatistics_format_variations',           test_tradestatistics_format_variations),
    ('test_version_format_variations',                   test_version_format_variations),
    ('test_backtestresult_format_variations',            test_backtestresult_format_variations),
    ('test_createoptimizationresponse_format_variations', test_createoptimizationresponse_format_variations),
    ('test_livealgorithm_format_variations',             test_livealgorithm_format_variations),
    ('test_livealgorithmresults_format_variations',      test_livealgorithmresults_format_variations),
    ('test_optimizationbacktest_format_variations',      test_optimizationbacktest_format_variations),
    ('test_order_format_variations',                     test_order_format_variations),
    ('test_project_lastlivedeployment_format_variations', test_project_lastlivedeployment_format_variations),
    ('test_optimization_format_variations',              test_optimization_format_variations),
    # Patch 4: Refinement tests
    ('test_patched_field_datetime_object_contract',      test_patched_field_datetime_object_contract),
    ('test_projectlist_response_b_iter5_failure_replication', test_projectlist_response_b_iter5_failure_replication),
]

for name, fn in tests:
    test(name, fn)

failed = [r for r in results if not r[0]]
print(f"\n{'=' * 60}")
print(f"{len(results)} tests, {len(failed)} failed")
sys.exit(1 if failed else 0)
