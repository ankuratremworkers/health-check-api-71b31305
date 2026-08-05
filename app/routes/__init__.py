"""Route barrel — every router the app serves is mounted here.

Adding a resource is two steps: create ``app/routes/<name>.py`` with a
module-level ``router``, then append one ``include_router`` line below. A route
file that is never mounted 404s silently.
"""

from fastapi import APIRouter

from app.routes import health

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
