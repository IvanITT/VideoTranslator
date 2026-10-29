"""Typed application errors with a human explanation and a recovery hint."""
from __future__ import annotations


class AppError(Exception):
    code = "app_error"
    status_code = 400

    def __init__(self, message: str, hint: str | None = None, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        if code:
            self.code = code

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint}


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class ConflictError(AppError):
    code = "conflict"
    status_code = 409


class MediaError(AppError):
    code = "media_error"
    status_code = 422


class ModelMissingError(AppError):
    code = "model_missing"
    status_code = 409


class ResourceError(AppError):
    code = "resource_error"
    status_code = 507


class SecurityError(AppError):
    code = "forbidden"
    status_code = 403


class CancelledError(AppError):
    code = "cancelled"
    status_code = 409
