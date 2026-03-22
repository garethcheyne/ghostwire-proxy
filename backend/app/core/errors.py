"""Standardized error handling for API responses."""

from fastapi import HTTPException, status


# Standard error messages for common scenarios
class ErrorMessages:
    """Standard error message constants."""

    # Authentication/Authorization
    INVALID_CREDENTIALS = "Invalid email or password"
    UNAUTHORIZED = "Authentication required"
    FORBIDDEN = "You do not have permission to access this resource"
    ACCOUNT_DISABLED = "Account is disabled"
    TOKEN_EXPIRED = "Token has expired"
    TOKEN_INVALID = "Invalid token"

    # Resources
    NOT_FOUND = "{resource} not found"
    ALREADY_EXISTS = "{resource} already exists"
    IN_USE = "{resource} is in use and cannot be deleted"

    # Validation
    VALIDATION_ERROR = "Validation error: {detail}"
    INVALID_INPUT = "Invalid input: {detail}"
    REQUIRED_FIELD = "Field '{field}' is required"

    # Server errors
    INTERNAL_ERROR = "An internal error occurred"
    SERVICE_UNAVAILABLE = "Service temporarily unavailable"
    DATABASE_ERROR = "Database operation failed"
    EXTERNAL_SERVICE_ERROR = "External service error: {service}"


def not_found_error(resource: str) -> HTTPException:
    """Raise a 404 Not Found error."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=ErrorMessages.NOT_FOUND.format(resource=resource),
    )


def already_exists_error(resource: str) -> HTTPException:
    """Raise a 409 Conflict error for duplicate resources."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=ErrorMessages.ALREADY_EXISTS.format(resource=resource),
    )


def validation_error(detail: str) -> HTTPException:
    """Raise a 400 Bad Request error for validation failures."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ErrorMessages.VALIDATION_ERROR.format(detail=detail),
    )


def unauthorized_error(detail: str = ErrorMessages.UNAUTHORIZED) -> HTTPException:
    """Raise a 401 Unauthorized error."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def forbidden_error(detail: str = ErrorMessages.FORBIDDEN) -> HTTPException:
    """Raise a 403 Forbidden error."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    )


def internal_error(detail: str = ErrorMessages.INTERNAL_ERROR) -> HTTPException:
    """Raise a 500 Internal Server Error."""
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    )


def in_use_error(resource: str) -> HTTPException:
    """Raise a 409 Conflict error for resources that cannot be deleted."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=ErrorMessages.IN_USE.format(resource=resource),
    )
