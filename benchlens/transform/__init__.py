"""Transform layer — schema mapping, validation, KPI normalization."""

from benchlens.transform.canonical import (
    COLUMN_TO_KPI,
    DENORM_KPI_COLUMNS,
    OPTIONAL_RUN_COLUMNS,
    REQUIRED_RUN_COLUMNS,
    STATUS_ALIAS,
)
from benchlens.transform.field_mapper import apply_field_mapping, strip_prefix
from benchlens.transform.kpi_normalizer import NormalizeResult, normalize
from benchlens.transform.pipeline import TransformResult, transform
from benchlens.transform.schema_validator import ValidationResult, validate_runs

__all__ = [
    "COLUMN_TO_KPI",
    "DENORM_KPI_COLUMNS",
    "OPTIONAL_RUN_COLUMNS",
    "REQUIRED_RUN_COLUMNS",
    "STATUS_ALIAS",
    "NormalizeResult",
    "TransformResult",
    "ValidationResult",
    "apply_field_mapping",
    "normalize",
    "strip_prefix",
    "transform",
    "validate_runs",
]

