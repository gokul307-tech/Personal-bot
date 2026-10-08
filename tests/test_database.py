from unittest.mock import Mock

import pytest

from app.services.user_service import create_user


def test_user_service_normalizes_name_and_email_before_persisting():
	db = Mock()

	user = create_user(db, "  Student Name  ", "  STUDENT@EXAMPLE.COM  ")

	assert user.name == "Student Name"
	assert user.email == "student@example.com"
	db.add.assert_called_once_with(user)
	db.commit.assert_called_once()


@pytest.mark.parametrize("name", ["", "   ", None])
def test_user_service_rejects_blank_names(name):
	with pytest.raises(ValueError, match="must not be blank"):
		create_user(Mock(), name)
