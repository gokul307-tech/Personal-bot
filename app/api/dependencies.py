from functools import lru_cache

from app.agent.agent import VDSSAgent
from app.agent.registry import create_default_registry
from app.memory.memory_manager import MemoryManager


@lru_cache(maxsize=1)
def get_agent() -> VDSSAgent:

    registry = create_default_registry()

    memory = MemoryManager()

    return VDSSAgent(
        registry=registry,
        memory_manager=memory,
    )