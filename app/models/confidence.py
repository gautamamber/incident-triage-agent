from typing import Literal

from pydantic import BaseModel


class ConfidenceScore(BaseModel):
    score: float
    band: Literal["high", "medium", "low"]
    signals: dict[str, float]  # signal name -> contribution, positive or negative
