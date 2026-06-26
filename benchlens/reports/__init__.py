"""Reporting layer: manage Power BI-facing SQL views.

The semantic views live in `benchlens/warehouse/migrations/003_reporting_views.sql`.
This module knows the expected view names and exposes operations to refresh,
inspect, and verify them.
"""

from __future__ import annotations

from .view_manager import (
    REPORTING_VIEWS,
    ViewInfo,
    check_views,
    refresh_views,
)

__all__ = ["REPORTING_VIEWS", "ViewInfo", "check_views", "refresh_views"]
