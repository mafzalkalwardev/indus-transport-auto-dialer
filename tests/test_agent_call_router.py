from src.agent_call_router import AgentCallRouter


def test_first_pickup_becomes_live():
    router = AgentCallRouter()
    assert router.on_pickup(0) == "live"
    assert router.agent_ears_slot() == 0
    assert router.waiting_count() == 0


def test_second_pickup_queues():
    router = AgentCallRouter()
    router.on_pickup(0)
    assert router.on_pickup(3) == "queued"
    assert router.agent_ears_slot() == 0
    assert router.queued_slots() == [3]


def test_release_promotes_next_waiting():
    router = AgentCallRouter()
    router.on_pickup(0)
    router.on_pickup(3)
    router.on_pickup(7)
    promoted = router.release_agent(0)
    assert promoted == 3
    assert router.agent_ears_slot() == 3
    assert router.queued_slots() == [7]


def test_remove_slot_promotes_when_live_drops():
    router = AgentCallRouter()
    router.on_pickup(1)
    router.on_pickup(2)
    promoted = router.remove_slot(1)
    assert promoted == 2
    assert router.agent_ears_slot() == 2


def test_reset_clears_state():
    router = AgentCallRouter()
    router.on_pickup(0)
    router.on_pickup(1)
    router.reset()
    assert router.agent_ears_slot() is None
    assert router.waiting_count() == 0
