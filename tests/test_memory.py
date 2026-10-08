import pytest

from app.memory.short_term import ShortTermMemory


def test_short_term_memory_zero_limit_retains_nothing():
	memory = ShortTermMemory(max_messages=0)

	memory.add("user", "temporary")

	assert memory.get_messages() == []


def test_short_term_memory_keeps_only_most_recent_messages():
	memory = ShortTermMemory(max_messages=2)
	for content in ("one", "two", "three"):
		memory.add("user", content)

	assert [message["content"] for message in memory.get_messages()] == ["two", "three"]


@pytest.mark.parametrize("limit", [-1, True, 1.5])
def test_short_term_memory_rejects_invalid_limits(limit):
	with pytest.raises(ValueError, match="non-negative integer"):
		ShortTermMemory(max_messages=limit)
