"""Liveness endpoint. The shape every other route module copies."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class Health(BaseModel):
    status: str


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")
