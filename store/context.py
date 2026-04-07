from pydantic import BaseModel
import random


# =========================
# CONTEXT
# =========================


class schedulingContext(BaseModel):
    """Context for scheduling agent."""
    user_name: str | None = None
    celphone: str | None = None
    email: str | None = None
    cpf: str | None = None
    codigo: int | None = None

def create_initial_context() -> schedulingContext:
    """
    Factory for a new schedulingContext.
    """
    ctx = schedulingContext()
    return ctx