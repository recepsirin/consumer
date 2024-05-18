import pytest

from consumer.client import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient(base_url="http://invalid.test-node")
