"""Compatibility shim — all LLM calls go through multi-provider brain."""
from app.services.llm import generate_json, generate_text

__all__ = ["generate_text", "generate_json"]
