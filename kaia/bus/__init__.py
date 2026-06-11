"""Agentic OS R-3 bus — A2A envelope protocol over Postgres LISTEN/NOTIFY.

Transport-pluggable: BusTransport Protocol is implemented by
PostgresBusTransport (prod) and InMemoryBusTransport (tests). The Bus
class owns RPC correlation + timeouts; nothing here imports telegram.
"""

from __future__ import annotations

from bus.envelope import Envelope, Visibility
from bus.transport import BusTransport, InMemoryBusTransport

__all__ = ["Envelope", "Visibility", "BusTransport", "InMemoryBusTransport"]
