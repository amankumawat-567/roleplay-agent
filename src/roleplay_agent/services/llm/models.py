from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    name: str
    num_ctx: int
