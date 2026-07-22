from packages.core.ids import global_id_bytes, make_global_id


def test_global_id_is_deterministic():
    a = make_global_id("KR", "KR-11680-10800-1-0045-0000-A-12-8499")
    b = make_global_id("KR", "KR-11680-10800-1-0045-0000-A-12-8499")
    assert a == b
    assert a.startswith("0x")
    assert len(a) == 66


def test_global_id_uppercases_country():
    assert make_global_id("kr", "X") == make_global_id("KR", "X")


def test_global_id_differs_per_canonical():
    assert make_global_id("KR", "A") != make_global_id("KR", "B")
    assert make_global_id("KR", "A") != make_global_id("AE", "A")


def test_global_id_bytes_roundtrip():
    gid = make_global_id("KR", "X")
    raw = global_id_bytes(gid)
    assert len(raw) == 32
    assert f"0x{raw.hex()}" == gid


def test_global_id_bytes_rejects_invalid():
    import pytest

    with pytest.raises(ValueError):
        global_id_bytes("not-an-id")
