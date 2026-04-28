"""
CSG-02 — Cross-script global propagation: Stata fix.

Regression tests verifying that globals defined in a parent Stata script are
inherited by child (and grandchild) scripts during multi-script parsing.

Scenarios covered:
  1. Single-level inheritance: child resolves $global defined in master
  2. Two-level (grandchild) inheritance: grandchild resolves $global from grandparent
  3. Chained globals: master defines $root; child defines $outdir "${root}/sub";
     grandchild uses $outdir — must resolve to full path
  4. Global redefinition: child redefines an inherited global; child's definition wins
  5. Cross-script globals fixture (integration test via extract-edges)
  6. Chained globals fixture (integration test via extract-edges)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts

FIXTURES = Path(__file__).parent / "fixtures"
CSG_FIXTURE = FIXTURES / "cross_script_globals"
CHAINED_FIXTURE = FIXTURES / "chained_globals"
INHERITED_FIXTURE = FIXTURES / "inherited_globals"


def _build(project_root: Path) -> object:
    """Build a GraphModel for all .do files found under project_root."""
    cfg = AppConfig()
    do_files = sorted(
        str(p.relative_to(project_root)).replace("\\", "/")
        for p in project_root.rglob("*.do")
    )
    return build_graph_from_scripts(
        project_root=project_root,
        script_files=do_files,
        exclusions=cfg.exclusions,
        parser_config=cfg.parser,
        normalization=cfg.normalization,
        classification_config=cfg.classification,
        display_config=cfg.display,
    )


def _edge_set(graph) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in graph.edges}


def _placeholder_nodes(graph) -> set[str]:
    return {nid for nid, n in graph.nodes.items() if n.node_type == "artifact_placeholder"}


# ---------------------------------------------------------------------------
# 1. Single-level inheritance
# ---------------------------------------------------------------------------

def test_single_level_global_inheritance_csg_fixture():
    """$ddir and $pdir defined in master.do must resolve in analysis/clean.do."""
    graph = _build(CSG_FIXTURE)
    edges = _edge_set(graph)

    # clean.do reads data/raw/survey.dta (ddir = data/raw)
    assert ("data/raw/survey.dta", "analysis/clean.do") in edges, (
        "Expected edge: data/raw/survey.dta → analysis/clean.do"
    )
    # clean.do writes output/survey_clean.dta (pdir = output)
    assert ("analysis/clean.do", "output/survey_clean.dta") in edges, (
        "Expected edge: analysis/clean.do → output/survey_clean.dta"
    )
    # regressions.do reads output/survey_clean.dta (pdir = output)
    assert ("output/survey_clean.dta", "analysis/regressions.do") in edges, (
        "Expected edge: output/survey_clean.dta → analysis/regressions.do"
    )


# ---------------------------------------------------------------------------
# 2. Two-level (grandparent → child) inheritance
# ---------------------------------------------------------------------------

def test_two_level_global_inheritance_csg_fixture():
    """$rootdir defined in master2.do; stage1.do builds $stagedir; stage1_sub.do uses it."""
    graph = _build(CSG_FIXTURE)
    edges = _edge_set(graph)

    # stage1_sub.do reads data/stage1/input.dta  (stagedir = rootdir/stage1 = data/stage1)
    assert ("data/stage1/input.dta", "pipeline/stage1_sub.do") in edges, (
        "Expected edge: data/stage1/input.dta → pipeline/stage1_sub.do"
    )
    # stage1_sub.do writes data/stage1/output.dta
    assert ("pipeline/stage1_sub.do", "data/stage1/output.dta") in edges, (
        "Expected edge: pipeline/stage1_sub.do → data/stage1/output.dta"
    )


def test_no_placeholder_nodes_in_csg_fixture():
    """After fix, no placeholder artifact nodes should remain in cross_script_globals."""
    graph = _build(CSG_FIXTURE)
    placeholders = _placeholder_nodes(graph)
    assert not placeholders, (
        f"Unexpected placeholder nodes after global propagation fix: {placeholders}"
    )


# ---------------------------------------------------------------------------
# 3. Chained globals: master $root → child $outdir → grandchild uses $outdir
# ---------------------------------------------------------------------------

def test_chained_globals_grandchild_resolves_outdir():
    """Grandchild stage1b.do uses $outdir which child stage1.do built from $root."""
    graph = _build(INHERITED_FIXTURE)
    edges = _edge_set(graph)

    # stage1.do: $outdir = "${root}/processed" = "data/project/processed"
    # stage1b.do reads ${outdir}/stage1_out.dta = data/project/processed/stage1_out.dta
    assert (
        "data/project/processed/stage1_out.dta",
        "grandchild/stage1b.do",
    ) in edges, (
        "Expected grandchild to inherit chained global $outdir from stage1.do"
    )
    # stage1b.do writes ${outdir}/stage1b_out.dta = data/project/processed/stage1b_out.dta
    assert (
        "grandchild/stage1b.do",
        "data/project/processed/stage1b_out.dta",
    ) in edges, (
        "Expected grandchild write edge using chained $outdir"
    )


def test_chained_globals_child_uses_inherited_root():
    """Child stage1.do's $outdir definition itself uses inherited $root from master."""
    graph = _build(INHERITED_FIXTURE)
    edges = _edge_set(graph)

    # stage1.do reads ${indir}/input.dta = data/raw/input.dta ($indir from master)
    assert ("data/raw/input.dta", "child/stage1.do") in edges, (
        "Expected child to resolve $indir inherited from master"
    )
    # stage1.do writes ${outdir}/stage1_out.dta = data/project/processed/stage1_out.dta
    assert ("child/stage1.do", "data/project/processed/stage1_out.dta") in edges, (
        "Expected child write edge using chained $outdir = ${root}/processed"
    )


# ---------------------------------------------------------------------------
# 4. Global redefinition in child (child's definition wins)
# ---------------------------------------------------------------------------

def test_global_redefinition_child_wins():
    """stage2.do redefines $root; its own definition should take precedence."""
    graph = _build(INHERITED_FIXTURE)
    edges = _edge_set(graph)

    # stage2.do redefines $root = "data/override" → reads data/override/other.dta
    assert ("data/override/other.dta", "child/stage2.do") in edges, (
        "Expected child's redefined $root to produce data/override/other.dta read edge"
    )
    assert ("child/stage2.do", "data/override/stage2_out.dta") in edges, (
        "Expected child's redefined $root to produce data/override/stage2_out.dta write edge"
    )
    # The master's $root = "data/project" should NOT appear as a read for stage2
    assert ("data/project/other.dta", "child/stage2.do") not in edges, (
        "Child's $root redefinition should shadow the parent's value"
    )


# ---------------------------------------------------------------------------
# 5 & 6. Integration: full fixture runs produce no partial-resolution diagnostics
# ---------------------------------------------------------------------------

def test_csg_fixture_no_partial_resolution_diagnostics():
    """No dynamic_path_partial_resolution diagnostics expected after the fix."""
    graph = _build(CSG_FIXTURE)
    partial = [
        d for d in graph.diagnostics
        if d.code == "dynamic_path_partial_resolution"
    ]
    assert not partial, (
        f"Unexpected partial-resolution diagnostics: {[(d.payload.get('script'), d.payload.get('pattern')) for d in partial]}"
    )


def test_chained_globals_fixture_master2_chain_resolves():
    """master2.do sets $proj and $datadir; clean.do (child) should resolve both."""
    graph = _build(CHAINED_FIXTURE)
    edges = _edge_set(graph)

    # master2: $proj=studies/welfare, $datadir="${proj}/data" = studies/welfare/data
    # clean.do: $rawdir="${datadir}/raw" = studies/welfare/data/raw
    # clean reads ${rawdir}/survey.dta = studies/welfare/data/raw/survey.dta
    assert (
        "studies/welfare/data/raw/survey.dta",
        "analysis/clean.do",
    ) in edges, (
        "Expected clean.do to resolve three-level chain: $rawdir → $datadir → $proj"
    )
    assert (
        "analysis/clean.do",
        "studies/welfare/data/clean/survey_clean.dta",
    ) in edges, (
        "Expected clean.do save edge using $datadir from master2"
    )
