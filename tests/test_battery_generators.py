from __future__ import annotations

from pathlib import Path

import pytest

from battery import controls, explore_repo, lookup_families, supplied_evidence
from evidence_harness.rules.deterministic import complete


@pytest.mark.parametrize(
    ("family", "item_id", "answer", "nonce"),
    [
        ("alias_resolution", "3f722d1394160fb2c26c", "543000", "nonce-frhefup7j7z3je"),
        ("priority_chain", "be67d6e0ea0f1a2b5646", "686912", "nonce-3hjk5wu95x7e3f"),
        ("index_routing", "d0cc4af792918723aa31", "132722", "nonce-3bphsy87kbeum7"),
        ("filtered_sum", "44e1973eedf299bf420a", "60", "nonce-y4q434rxuw37bb"),
        ("single_lookup", "1dd19b570d70128793e9", "45344", "nonce-352pct3jdhy8g8"),
        ("two_file_join", "9926f4e795ded19af7dc", "889705", "nonce-nr9uxgkgraf33d"),
    ],
)
def test_lookup_port_has_frozen_seed_zero_values(
    family: str, item_id: str, answer: str, nonce: str
) -> None:
    item = lookup_families.generate_lineage(family, 0)

    assert set(item) == {"id", "family", "seed", "files", "question", "gold"}
    assert item["id"] == item_id
    assert item["gold"] == {"answer": answer, "nonce": nonce}


@pytest.mark.parametrize(
    "generator",
    [
        lookup_families.generate_items,
        explore_repo.generate_items,
        controls.generate_items,
        supplied_evidence.generate_items,
    ],
)
def test_generators_are_deterministic(generator) -> None:
    assert generator(seed=7, n=8) == generator(seed=7, n=8)
    assert generator(seed=7, n=8) != generator(seed=8, n=8)


def test_materialize_writes_only_declared_files(tmp_path: Path) -> None:
    item = lookup_families.generate_lineage("single_lookup", 3)

    lookup_families.materialize(item, tmp_path)

    relative_paths = {
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()
    }
    assert relative_paths == set(item["files"])
    assert not any("gold" in path.parts for path in tmp_path.rglob("*"))


def test_explore_items_cover_deep_and_shallow_positions() -> None:
    deep, shallow = explore_repo.generate_items(seed=2, n=2)

    assert deep["family"] == "deep"
    assert deep["gold"]["position"] > 8_000
    assert shallow["family"] == "shallow"
    assert shallow["gold"]["position"] < 8_000
    for item in (deep, shallow):
        assert 10 <= len(item["files"]) <= 40
        assert 20 <= len(item["gold"]["sentence"]) <= 200
        source = item["files"][item["gold"]["path"]]
        assert source.index(item["gold"]["sentence"]) == item["gold"]["position"]
        assert item["gold"]["answer"] not in item["files"][next(
            path for path in item["files"] if path.startswith("README-")
        )]


def test_controls_define_abstention_authority_and_name_boundary() -> None:
    absence, authority, name = controls.generate_items(seed=0, n=3)

    assert absence["gold"]["abstain"] is True
    assert all(absence["question"].split()[1] not in text for text in absence["files"].values())
    assert authority["gold"]["answer"] in authority["files"]["policy/authority.md"]
    assert authority["gold"]["answer"] not in authority["files"]["README.md"]
    assert name["gold"]["rules_expected_nonlanding"] is True

    service_path = f"services/{name['gold']['answer']}.ini"
    rounds = [{
        "executions": [{
            "name": "read_file",
            "arguments": f'{{"path":"{service_path}"}}',
            "result": {"content": name["files"][service_path]},
        }]
    }]
    ruled = complete(name["gold"]["answer"], rounds, [service_path])
    assert ruled["answer"] is None
    assert ruled["nonlanded_by_type_check"] is True


def test_supplied_items_are_evidence_swap_pairs() -> None:
    for item in supplied_evidence.generate_items(seed=4, n=2):
        first = item["variants"]["A"]["files"]
        second = item["variants"]["B"]["files"]
        assert set(first) == set(second)
        assert first != second
        assert item["gold"]["A"]["answer"] != item["gold"]["B"]["answer"]
        assert item["gold"]["A"]["nonce"] == item["gold"]["B"]["nonce"]
