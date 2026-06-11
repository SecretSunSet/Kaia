"""Agentic OS R-3 bus — A2A envelope protocol over Postgres LISTEN/NOTIFY.

Transport-pluggable: BusTransport Protocol is implemented by
PostgresBusTransport (prod) and InMemoryBusTransport (tests). The Bus
class owns RPC correlation + timeouts; nothing here imports telegram.
"""

from __future__ import annotations

from agent_runtime.base_agent import PeerCallError, PeerCallTimeoutError
from bus.bus import Bus
from bus.envelope import Envelope, Visibility
from bus.transport import BusTransport, InMemoryBusTransport

__all__ = [
    "Bus",
    "BusTransport",
    "Envelope",
    "InMemoryBusTransport",
    "PeerCallError",
    "PeerCallTimeoutError",
    "Visibility",
]
