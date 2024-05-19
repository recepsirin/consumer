from unittest.mock import AsyncMock

import httpx
import pytest

from consumer.coordinator import TransactionCoordinator, TransactionState


@pytest.fixture
def coordinator() -> TransactionCoordinator:
    return TransactionCoordinator()


@pytest.mark.asyncio
async def test_create_already_exists(coordinator: TransactionCoordinator) -> None:
    # Test that the group already exists on all nodes
    mock_request = AsyncMock(spec=httpx.Request)
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 400  # Simulate a 400 status code

    # Instantiate HTTPStatusError with the mock request and response
    http_error = httpx.HTTPStatusError("The object exists", request=mock_request, response=mock_response)

    coordinator.client1.post = AsyncMock(return_value=http_error)  # type: ignore[method-assign]
    coordinator.client2.post = AsyncMock(return_value=http_error)  # type: ignore[method-assign]
    coordinator.client3.post = AsyncMock(return_value=http_error)  # type: ignore[method-assign]

    group_id = "12"
    state = await coordinator.create(group_id)

    assert state == TransactionState.SUCCEEDED


@pytest.mark.asyncio
async def test_coordinate_create_success(coordinator: TransactionCoordinator) -> None:
    coordinator.client1.post = AsyncMock(return_value=httpx.Response(201))  # type: ignore[method-assign]
    coordinator.client2.post = AsyncMock(return_value=httpx.Response(201))  # type: ignore[method-assign]
    coordinator.client3.post = AsyncMock(return_value=httpx.Response(201))  # type: ignore[method-assign]

    group_id = "test_group_id"
    action = "create"
    state = await coordinator.coordinate(group_id, action)

    assert state == TransactionState.SUCCEEDED


@pytest.mark.asyncio
async def test_coordinate_create_retry_required_then_succeeded(coordinator: TransactionCoordinator) -> None:
    coordinator.client1.post = AsyncMock(  # type: ignore[method-assign]
        side_effect=[httpx.Response(500), httpx.Response(201)]
    )
    coordinator.client2.post = AsyncMock(  # type: ignore[method-assign]
        side_effect=[httpx.Response(500), httpx.Response(201)]
    )
    coordinator.client3.post = AsyncMock(  # type: ignore[method-assign]
        side_effect=[httpx.Response(500), httpx.Response(201)]
    )

    group_id = "10"
    action = "create"
    state = await coordinator.coordinate(group_id, action)

    assert state == TransactionState.SUCCEEDED
