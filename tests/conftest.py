import pytest

from scripts.mock_fixtures import mock_settings


@pytest.fixture
def settings():
    return mock_settings()
