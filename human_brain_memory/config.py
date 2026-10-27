from dataclasses import dataclass, fields


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool = True
    inject_limit: int = 12
    context_chars: int = 6000
    episode_idle_minutes: int = 30
    episode_min_messages: int = 2
    batch_messages: int = 80
    message_chars: int = 4000
    consolidate_hour: int = 4
    timezone: str = "Asia/Shanghai"
    forget: bool = True
    emotions: bool = True
    gist: bool = True
    followups: bool = True
    semantic_floor: float = 0.55
    semantic_ceiling: float = 0.75
    llm_timeout: int = 90
    embedding_timeout: int = 5
    backup_keep: int = 7

    def __post_init__(self):
        for name, low, high in (
            ("inject_limit", 1, 100), ("context_chars", 500, 50000),
            ("episode_idle_minutes", 1, 1440), ("episode_min_messages", 1, 100),
            ("batch_messages", 2, 500), ("message_chars", 100, 20000),
            ("consolidate_hour", 0, 23), ("llm_timeout", 5, 600),
            ("embedding_timeout", 1, 60), ("backup_keep", 1, 100),
        ):
            if not isinstance(getattr(self, name), int) or not low <= getattr(self, name) <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
        if not -1 <= self.semantic_floor < self.semantic_ceiling <= 1:
            raise ValueError("semantic_floor must be smaller than semantic_ceiling, within [-1, 1]")
        from zoneinfo import ZoneInfo
        ZoneInfo(self.timezone)

    @classmethod
    def from_mapping(cls, value):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in value.items() if k in names})
