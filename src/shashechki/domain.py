"""Общие единицы, идентификаторы и ошибки на границах системы."""
from dataclasses import dataclass, field
from typing import Any
import re

SCHEMA_VERSION = "1.0"
MODEL_VERSION = "1.0.0"
ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")
TERMINAL = {"completed", "cancelled", "expired", "failed"}
DEFAULT_CONFIG = {
    "allocation": "central", "conflict_policy": "first_acceptable",
    "rating_policy": "off", "protection_profile": "protected",
    "limits": {"horizon_ms":86400000,"max_events":1000000,"max_pending_events":100000},
    "deadlines": {"allocation_window_ms":2000,"consent_window_ms":2000,"round_ms":2000,
                  "pickup_grace_ms":5000,"max_rounds":3,"max_reassignments":2,"telemetry_interval_ms":5000},
    "weights": {"wait_kopecks_per_ms":{"numerator":1,"denominator":60},"driver_rating_kopecks":1000},
}

class InputError(ValueError):
    def __init__(self, message, path="", code="INVALID_INPUT"):
        super().__init__(message)
        self.code, self.path = code, path
    def detail(self):
        return {"path":self.path,"code":self.code,"message":str(self)}

@dataclass
class Agent:
    id: str
    role: str
    state: str = "idle"
    knowledge: dict[str,Any] = field(default_factory=dict)

@dataclass
class Run:
    inputs: dict
    config: dict
    trace: list
    orders: list
    drivers: list
    metrics: dict
    playback: dict
    termination_reason: str
    fault_results: list = field(default_factory=list)
