import pytest

from app.api.auth import require_authenticated
from app.api.auth_context import reset_current_user_id, set_current_user_id
from app.main import app


async def _authenticated_test_owner():
    token = set_current_user_id(1)
    try:
        yield {"id": 1, "username": "test-owner"}
    finally:
        reset_current_user_id(token)


@pytest.fixture(autouse=True)
def authenticated_legacy_owner_for_existing_api_tests(request):
    if request.module.__name__.endswith("test_auth"):
        yield
        return
    missing = object()
    previous = app.dependency_overrides.get(require_authenticated, missing)
    app.dependency_overrides[require_authenticated] = _authenticated_test_owner
    try:
        yield
    finally:
        if previous is missing:
            app.dependency_overrides.pop(require_authenticated, None)
        else:
            app.dependency_overrides[require_authenticated] = previous