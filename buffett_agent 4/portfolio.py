"""
portfolio.py — a tiny local, file-backed portfolio tracker.

No brokerage connection, no order placement — this only tracks what you tell
it you hold (ticker, shares, cost basis) in a local JSON file next to this
script, and lets the app compute live value / gain-loss / strategy scores
against your actual holdings. You remain the only one who ever places a
trade.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_data.json")


@dataclass
class Holding:
    ticker: str
    shares: float
    cost_basis_per_share: Optional[float] = None
    note: str = ""
    added_at: str = ""


class Portfolio:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.holdings: list = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                raw = json.load(f)
            self.holdings = [Holding(**h) for h in raw]

    def _save(self):
        with open(self.path, "w") as f:
            json.dump([asdict(h) for h in self.holdings], f, indent=2)

    def add(self, ticker: str, shares: float, cost_basis_per_share: Optional[float] = None, note: str = ""):
        ticker = ticker.upper().strip()
        for h in self.holdings:
            if h.ticker == ticker:
                # Merge: weighted-average cost basis, add shares
                total_shares = h.shares + shares
                if h.cost_basis_per_share is not None and cost_basis_per_share is not None and total_shares:
                    h.cost_basis_per_share = (
                        h.shares * h.cost_basis_per_share + shares * cost_basis_per_share
                    ) / total_shares
                h.shares = total_shares
                self._save()
                return
        self.holdings.append(Holding(
            ticker=ticker, shares=shares, cost_basis_per_share=cost_basis_per_share,
            note=note, added_at=datetime.now(timezone.utc).isoformat(),
        ))
        self._save()

    def remove(self, ticker: str):
        ticker = ticker.upper().strip()
        self.holdings = [h for h in self.holdings if h.ticker != ticker]
        self._save()

    def set_shares(self, ticker: str, shares: float):
        ticker = ticker.upper().strip()
        for h in self.holdings:
            if h.ticker == ticker:
                h.shares = shares
        self._save()

    def list(self):
        return list(self.holdings)
