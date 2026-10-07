"""Structured completion data for engineering operations."""
from dataclasses import dataclass


@dataclass
class OperationResult:
    summary: str
    output_path: str = ""
    successful: int = 0
    skipped: int = 0
    failed: int = 0

    def __str__(self):
        return self.summary

    def __contains__(self, value):
        return value in self.summary
