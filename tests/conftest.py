from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def molit_fixture():
    def load(name: str) -> bytes:
        return (FIXTURES / "molit" / name).read_bytes()

    return load
