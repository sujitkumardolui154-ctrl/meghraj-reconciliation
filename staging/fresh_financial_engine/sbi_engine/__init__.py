"""SBI Reconciliation — isolated synthetic-only fresh implementation.

No production writer, filesystem input, bank, cloud or historical data access.
"""
from .engine import evaluate, EngineBlocked
__all__ = ["evaluate", "EngineBlocked"]