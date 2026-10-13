from dataclasses import dataclass
from datetime import datetime

from lighter_tracker.models.trader import (
    TraderCandidate,
)


@dataclass(frozen=True)
class LeaderboardPage:
    total: int

    updated_at: datetime

    fetched_at: datetime

    candidates: tuple[TraderCandidate, ...]