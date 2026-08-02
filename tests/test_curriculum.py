"""Tests for the curriculum loader — validation and mission-grounded invariant."""
from __future__ import annotations

from pathlib import Path

import pytest

from coach.config import ChallengeType, Difficulty
from coach.curriculum import CurriculumNode, load_curriculum


def _write_curriculum(tmp_path: Path, nodes: list[dict]) -> Path:
    import yaml
    p = tmp_path / "test-curriculum.yaml"
    p.write_text(yaml.safe_dump(nodes))
    return p


def _valid_node(**overrides) -> dict:
    base = {
        "id": "ai-fluency/test-node",
        "gap": "AI technical fluency",
        "concept": "Test concept",
        "difficulty": "medium",
        "source": [{"url": "https://example.com", "type": "report",
                     "accessed_at": "2026-08-01", "anchor": "test anchor"}],
        "related_gaps": [],
        "prerequisites": [],
        "challenge_types": ["concept-recall"],
        "phase": 1,
    }
    base.update(overrides)
    return base


class TestLoadCurriculum:
    def test_loads_all_nodes(self, tmp_path):
        path = _write_curriculum(tmp_path, [_valid_node(), _valid_node(id="ai-fluency/second")])
        nodes = load_curriculum(path)
        assert len(nodes) == 2
        assert nodes[0].id == "ai-fluency/test-node"

    def test_parses_difficulty_enum(self, tmp_path):
        path = _write_curriculum(tmp_path, [_valid_node(difficulty="hard")])
        nodes = load_curriculum(path)
        assert nodes[0].difficulty == Difficulty.HARD

    def test_parses_challenge_types(self, tmp_path):
        path = _write_curriculum(tmp_path, [
            _valid_node(challenge_types=["concept-recall", "scenario"])
        ])
        nodes = load_curriculum(path)
        assert ChallengeType.SCENARIO in nodes[0].challenge_types

    def test_root_node_has_no_prerequisites(self, tmp_path):
        path = _write_curriculum(tmp_path, [_valid_node(prerequisites=[])])
        nodes = load_curriculum(path)
        assert nodes[0].is_root is True

    def test_non_root_node(self, tmp_path):
        path = _write_curriculum(tmp_path, [
            _valid_node(id="ai-fluency/root"),
            _valid_node(id="ai-fluency/child", prerequisites=["ai-fluency/root"]),
        ])
        nodes = load_curriculum(path)
        assert nodes[1].is_root is False
        assert nodes[1].prerequisites == ["ai-fluency/root"]


class TestMissionGrounded:
    def test_node_with_gap_and_source_passes(self, tmp_path):
        path = _write_curriculum(tmp_path, [_valid_node()])
        nodes = load_curriculum(path)
        assert nodes[0].has_gap_and_source is True

    def test_node_missing_gap_raises(self, tmp_path):
        node = _valid_node()
        del node["gap"]
        path = _write_curriculum(tmp_path, [node])
        with pytest.raises(ValueError, match="mission-grounded"):
            load_curriculum(path)

    def test_node_missing_source_raises(self, tmp_path):
        node = _valid_node()
        del node["source"]
        path = _write_curriculum(tmp_path, [node])
        with pytest.raises(ValueError, match="mission-grounded"):
            load_curriculum(path)

    def test_node_empty_source_raises(self, tmp_path):
        path = _write_curriculum(tmp_path, [_valid_node(source=[])])
        with pytest.raises(ValueError, match="mission-grounded"):
            load_curriculum(path)


class TestInvalidValues:
    def test_invalid_difficulty_raises(self, tmp_path):
        path = _write_curriculum(tmp_path, [_valid_node(difficulty="impossible")])
        with pytest.raises(ValueError, match="invalid difficulty"):
            load_curriculum(path)

    def test_invalid_challenge_type_raises(self, tmp_path):
        path = _write_curriculum(tmp_path, [_valid_node(challenge_types=["bogus"])])
        with pytest.raises(ValueError, match="invalid challenge_type"):
            load_curriculum(path)


class TestRealCurriculum:
    def test_loads_committed_curriculum(self):
        from coach.config import CURRICULUM_PATH
        if CURRICULUM_PATH.exists():
            nodes = load_curriculum(CURRICULUM_PATH)
            assert len(nodes) == 22
            assert all(n.has_gap_and_source for n in nodes)
