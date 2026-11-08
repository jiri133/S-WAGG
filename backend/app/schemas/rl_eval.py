"""Shape of the RL battery evaluation summary read from ``RL/artifacts/reports``."""

from pydantic import BaseModel


class RlStrategyResult(BaseModel):
    """Per (strategy, mode) means over the per-day rows of ``results.csv``."""

    strategy: str
    mode: str
    runs: int
    days: int
    score_mean: float
    score_std: float
    net_cost_mean: float
    export_revenue_mean: float
    throughput_mean: float
    cycles_mean: float
    self_consumption_mean: float
    # LLM telemetry, only present on llm rows.
    feasible_rate: float | None = None
    invalid_rate: float | None = None
    tool_calls_per_day: float | None = None
    tokens_per_day: float | None = None
    latency_s_per_day: float | None = None
    cost_ron_per_day: float | None = None


class RlSplitReport(BaseModel):
    split: str
    days: int
    runs: int
    repeats: int | None = None
    seed: int | None = None
    created_utc: str | None = None
    farm: str | None = None
    results: list[RlStrategyResult]


class RlEvalReport(BaseModel):
    splits: list[RlSplitReport]
