from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import uuid

@dataclass
class TaskStep:
    id: str
    description: str
    status: str = "pending"  # pending, in_progress, complete, failed
    result: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskStep':
        return cls(**data)

@dataclass
class TaskPlan:
    id: str
    original_request: str
    reasoning: str
    steps: List[TaskStep]
    current_step_index: int = 0
    status: str = "active"  # active, complete, abandoned, failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'steps': [step.to_dict() for step in self.steps]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskPlan':
        steps_data = data.pop('steps', [])
        steps = [TaskStep.from_dict(s) for s in steps_data]
        return cls(steps=steps, **data)

    def get_current_step(self) -> Optional[TaskStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance_step(self):
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            self.updated_at = datetime.now(timezone.utc).isoformat()
        elif self.current_step_index == len(self.steps) - 1:
            self.status = "complete"
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_step_complete(self, result: str):
        step = self.get_current_step()
        if step:
            step.status = "complete"
            step.result = result
            step.completed_at = datetime.now(timezone.utc).isoformat()
            self.advance_step()
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_step_failed(self, error: str):
        step = self.get_current_step()
        if step:
            step.status = "failed"
            step.result = error
            self.status = "failed"
            self.updated_at = datetime.now(timezone.utc).isoformat()
