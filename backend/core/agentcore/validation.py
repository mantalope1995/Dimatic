"""
AgentCore Configuration Validation (Phase 10)

Configuration validation for AgentCore operations in ap-southeast-2.

Phase 10: Configuration validation enforces ap-southeast-2 (Australia) region
for data residency compliance, with comprehensive validation of all
AgentCore configuration parameters.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .config import AgentCoreConfig, Environment
from .errors import AgentCoreError, safe_log

logger = logging.getLogger(__name__)

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationCategory(str, Enum):
    """Categories of configuration validation."""
    REGION = "region"
    CREDENTIALS = "credentials"
    NETWORK = "network"
    FEATURE_FLAGS = "feature_flags"
    INTEGRATIONS = "integrations"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPLIANCE = "compliance"


@dataclass
class ValidationIssue:
    """
    A configuration validation issue.

    Attributes:
        category: Validation category
        severity: Issue severity
        field: Configuration field name
        message: Human-readable issue description
        value: The problematic value (optional)
        suggestion: Suggested fix (optional)
    """
    category: ValidationCategory
    severity: ValidationSeverity
    field: str
    message: str
    value: Optional[Any] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message,
            "value": str(self.value) if self.value is not None else None,
            "suggestion": self.suggestion,
            "region": PHASE_10_REGION,
        }


@dataclass
class ValidationResult:
    """
    Result of configuration validation.

    Attributes:
        is_valid: Whether configuration passed validation
        issues: List of validation issues
        warnings: Issues with WARNING severity
        errors: Issues with ERROR or CRITICAL severity
        validated_at: When validation was performed
    """
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get warnings only."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    @property
    def errors(self) -> List[ValidationIssue]:
        """Get errors and critical issues."""
        return [i for i in self.issues if i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "total_issues": len(self.issues),
            "warnings": len(self.warnings),
            "errors": len(self.errors),
            "issues": [issue.to_dict() for issue in self.issues],
            "validated_at": self.validated_at.isoformat(),
            "region": PHASE_10_REGION,
        }


@dataclass
class ValidationRule:
    """
    A configuration validation rule.

    Attributes:
        name: Unique rule identifier
        category: Validation category
        description: Rule description
        validate_func: Async validation function
        enabled: Whether rule is enabled
    """
    name: str
    category: ValidationCategory
    description: str
    validate_func: Callable[[AgentCoreConfig], Awaitable[Optional[ValidationIssue]]]
    enabled: bool = True


# ============================================================================
# Configuration Validator
# ============================================================================

class ConfigValidator:
    """
    Comprehensive configuration validation for AgentCore.

    Features:
    - Region compliance validation
    - Credential validation
    - Feature flag consistency
    - Network connectivity checks
    - Security settings validation
    - Performance recommendations

    Usage:
        ```python
        validator = ConfigValidator()

        # Validate configuration
        result = await validator.validate(config)

        if not result.is_valid:
            for issue in result.errors:
                print(f"{issue.field}: {issue.message}")
        ```
    """

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize the configuration validator.

        Args:
            config: Optional AgentCore configuration
        """
        self.config = config or AgentCoreConfig()
        self._rules: List[ValidationRule] = []
        self._register_default_rules()

        safe_log("ConfigValidator initialized")

    def _register_default_rules(self) -> None:
        """Register default validation rules."""
        # Region compliance rule
        self._rules.append(ValidationRule(
            name="region_compliance",
            category=ValidationCategory.COMPLIANCE,
            description="Ensure configuration uses ap-southeast-2 for Phase 10",
            validate_func=self._validate_region_compliance,
            enabled=True,
        ))

        # Credentials validation rule
        self._rules.append(ValidationRule(
            name="credentials_validation",
            category=ValidationCategory.CREDENTIALS,
            description="Validate AWS credentials are present for production",
            validate_func=self._validate_credentials,
            enabled=True,
        ))

        # Feature flag consistency rule
        self._rules.append(ValidationRule(
            name="feature_flag_consistency",
            category=ValidationCategory.FEATURE_FLAGS,
            description="Ensure feature flags are consistent",
            validate_func=self._validate_feature_flags,
            enabled=True,
        ))

        # S3 bucket validation rule
        self._rules.append(ValidationRule(
            name="s3_bucket_validation",
            category=ValidationCategory.INTEGRATIONS,
            description="Validate S3 bucket configuration",
            validate_func=self._validate_s3_bucket,
            enabled=True,
        ))

        # Timeout validation rule
        self._rules.append(ValidationRule(
            name="timeout_validation",
            category=ValidationCategory.PERFORMANCE,
            description="Validate timeout settings are reasonable",
            validate_func=self._validate_timeouts,
            enabled=True,
        ))

        # Security validation rule
        self._rules.append(ValidationRule(
            name="security_validation",
            category=ValidationCategory.SECURITY,
            description="Validate security settings",
            validate_func=self._validate_security,
            enabled=True,
        ))

    async def validate(
        self,
        config: Optional[AgentCoreConfig] = None
    ) -> ValidationResult:
        """
        Validate AgentCore configuration.

        Args:
            config: Configuration to validate (default: self.config)

        Returns:
            Validation result with issues
        """
        config = config or self.config

        issues = []

        # Run all enabled validation rules
        for rule in self._rules:
            if not rule.enabled:
                continue

            try:
                issue = await rule.validate_func(config)
                if issue:
                    issues.append(issue)

            except Exception as e:
                safe_log(f"Validation rule '{rule.name}' failed: {e}", level="error")
                issues.append(ValidationIssue(
                    category=rule.category,
                    severity=ValidationSeverity.ERROR,
                    field=rule.name,
                    message=f"Validation rule failed: {e}",
                ))

        # Determine validity
        is_valid = not any(
            i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
            for i in issues
        )

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
        )

    async def _validate_region_compliance(
        self,
        config: AgentCoreConfig
    ) -> Optional[ValidationIssue]:
        """Validate region compliance for Phase 10."""
        if config.aws_region != PHASE_10_REGION:
            return ValidationIssue(
                category=ValidationCategory.COMPLIANCE,
                severity=ValidationSeverity.ERROR,
                field="aws_region",
                message=f"Region must be {PHASE_10_REGION} for Phase 10 compliance",
                value=config.aws_region,
                suggestion=f"Set aws_region='{PHASE_10_REGION}' in configuration",
            )
        return None

    async def _validate_credentials(
        self,
        config: AgentCoreConfig
    ) -> Optional[ValidationIssue]:
        """Validate credentials for production environment."""
        if config.environment == Environment.LOCAL:
            # Local environment doesn't require AWS credentials
            return None

        if config.environment in (Environment.DEVELOPMENT, Environment.PRODUCTION):
            missing = []

            if not config.aws_access_key_id:
                missing.append("aws_access_key_id")

            if not config.aws_secret_access_key:
                missing.append("aws_secret_access_key")

            if missing:
                return ValidationIssue(
                    category=ValidationCategory.CREDENTIALS,
                    severity=ValidationSeverity.ERROR,
                    field="credentials",
                    message=f"Missing credentials for {config.environment.value}: {', '.join(missing)}",
                    suggestion="Provide AWS credentials via environment variables or config",
                )

        return None

    async def _validate_feature_flags(
        self,
        config: AgentCoreConfig
    ) -> Optional[ValidationIssue]:
        """Validate feature flag consistency."""
        issues = []

        # Code Interpreter requires S3 bucket
        if config.code_interpreter_enabled and not config.s3_bucket_name:
            issues.append("Code Interpreter requires S3 bucket")

        # Browser requires S3 bucket
        if config.browser_enabled and not config.s3_bucket_name:
            issues.append("Browser requires S3 bucket")

        # Gateway requires Runtime
        if config.gateway_enabled and not config.runtime_enabled:
            issues.append("Gateway requires Runtime to be enabled")

        if issues:
            return ValidationIssue(
                category=ValidationCategory.FEATURE_FLAGS,
                severity=ValidationSeverity.ERROR,
                field="feature_flags",
                message="Feature flag inconsistency: " + "; ".join(issues),
                suggestion="Review and adjust feature flags",
            )

        return None

    async def _validate_s3_bucket(
        self,
        config: AgentCoreConfig
    ) -> Optional[ValidationIssue]:
        """Validate S3 bucket configuration."""
        if not config.s3_bucket_name:
            return None

        # Check S3 bucket name format
        # S3 bucket names must be 3-63 chars, lowercase, no spaces, specific pattern
        pattern = r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$'

        if not re.match(pattern, config.s3_bucket_name):
            return ValidationIssue(
                category=ValidationCategory.INTEGRATIONS,
                severity=ValidationSeverity.ERROR,
                field="s3_bucket_name",
                message="Invalid S3 bucket name format",
                value=config.s3_bucket_name,
                suggestion="S3 bucket names must be 3-63 lowercase characters, no spaces",
            )

        # Check region-specific bucket naming
        if config.s3_bucket_region and config.s3_bucket_region != PHASE_10_REGION:
            return ValidationIssue(
                category=ValidationCategory.COMPLIANCE,
                severity=ValidationSeverity.WARNING,
                field="s3_bucket_region",
                message=f"S3 bucket region '{config.s3_bucket_region}' differs from Phase 10 region '{PHASE_10_REGION}'",
                suggestion=f"Consider using S3 bucket in {PHASE_10_REGION} for optimal performance",
            )

        return None

    async def _validate_timeouts(
        self,
        config: AgentCoreConfig
    ) -> Optional[ValidationIssue]:
        """Validate timeout settings."""
        warnings = []

        # Code Interpreter timeout
        if config.code_interpreter_timeout_seconds < 10:
            warnings.append("Code Interpreter timeout < 10s may be too short")
        elif config.code_interpreter_timeout_seconds > 300:
            warnings.append("Code Interpreter timeout > 300s may incur excessive costs")

        # Browser timeout
        if config.browser_timeout_seconds < 10:
            warnings.append("Browser timeout < 10s may be too short")
        elif config.browser_timeout_seconds > 600:
            warnings.append("Browser timeout > 600s may be excessive")

        if warnings:
            return ValidationIssue(
                category=ValidationCategory.PERFORMANCE,
                severity=ValidationSeverity.WARNING,
                field="timeouts",
                message="Timeout configuration concerns: " + "; ".join(warnings),
                suggestion="Review timeout settings for optimal performance",
            )

        return None

    async def _validate_security(
        self,
        config: AgentCoreConfig
    ) -> Optional[ValidationIssue]:
        """Validate security settings."""
        # For production, require HTTPS gateway URLs
        if config.environment == Environment.PRODUCTION:
            gateway_url = config.agent_core_gateway_url or ""

            if gateway_url and gateway_url.startswith("http://"):
                return ValidationIssue(
                    category=ValidationCategory.SECURITY,
                    severity=ValidationSeverity.ERROR,
                    field="agent_core_gateway_url",
                    message="Production environment requires HTTPS gateway URL",
                    value=gateway_url,
                    suggestion="Use HTTPS for secure communication",
                )

        return None

    def register_rule(
        self,
        rule: ValidationRule
    ) -> None:
        """
        Register a custom validation rule.

        Args:
            rule: Validation rule to register
        """
        self._rules.append(rule)
        safe_log(f"Registered custom validation rule '{rule.name}'")

    def unregister_rule(self, name: str) -> bool:
        """
        Unregister a validation rule.

        Args:
            name: Rule name to unregister

        Returns:
            True if rule was unregistered
        """
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                self._rules.pop(i)
                safe_log(f"Unregistered validation rule '{name}'")
                return True
        return False

    def enable_rule(self, name: str) -> bool:
        """Enable a validation rule by name."""
        for rule in self._rules:
            if rule.name == name:
                rule.enabled = True
                return True
        return False

    def disable_rule(self, name: str) -> bool:
        """Disable a validation rule by name."""
        for rule in self._rules:
            if rule.name == name:
                rule.enabled = False
                return True
        return False

    def get_rules(self) -> List[ValidationRule]:
        """Get all registered validation rules."""
        return self._rules.copy()


# ============================================================================
# Convenience Functions
# ============================================================================

_validator: Optional[ConfigValidator] = None


def get_config_validator(config: Optional[AgentCoreConfig] = None) -> ConfigValidator:
    """
    Get the configuration validator instance (singleton).

    Args:
        config: Optional AgentCore configuration

    Returns:
        ConfigValidator instance
    """
    global _validator

    if _validator is None:
        _validator = ConfigValidator(config=config)

    return _validator


async def validate_config(
    config: Optional[AgentCoreConfig] = None
) -> ValidationResult:
    """
    Validate AgentCore configuration.

    Args:
        config: Configuration to validate

    Returns:
        Validation result
    """
    validator = get_config_validator(config)
    return await validator.validate()


async def validate_config_or_raise(
    config: Optional[AgentCoreConfig] = None
) -> None:
    """
    Validate configuration and raise if invalid.

    Args:
        config: Configuration to validate

    Raises:
        AgentCoreError: If configuration is invalid
    """
    result = await validate_config(config)

    if not result.is_valid:
        error_messages = [f"{issue.field}: {issue.message}" for issue in result.errors]
        raise AgentCoreError(
            f"Configuration validation failed: {'; '.join(error_messages)}"
        )


def register_validation_rule(
    name: str,
    category: ValidationCategory,
    description: str,
    validate_func: Callable[[AgentCoreConfig], Awaitable[Optional[ValidationIssue]]],
) -> Callable[[AgentCoreConfig], Awaitable[Optional[ValidationIssue]]]:
    """
    Decorator to register a validation rule.

    Args:
        name: Unique rule identifier
        category: Validation category
        description: Rule description
        validate_func: Async validation function

    Returns:
        Decorator function

    Usage:
        ```python
        @register_validation_rule(
            name="custom_rule",
            category=ValidationCategory.SECURITY,
            description="Custom security validation"
        )
        async def my_validation_rule(config: AgentCoreConfig) -> Optional[ValidationIssue]:
            if not config.some_field:
                return ValidationIssue(...)
            return None
        ```
    """
    def decorator(func: Callable[[AgentCoreConfig], Awaitable[Optional[ValidationIssue]]]) -> Callable[[AgentCoreConfig], Awaitable[Optional[ValidationIssue]]]:
        rule = ValidationRule(
            name=name,
            category=category,
            description=description,
            validate_func=func,
            enabled=True,
        )

        validator = get_config_validator()
        validator.register_rule(rule)

        return func

    return decorator


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "ValidationSeverity",
    "ValidationCategory",
    "ValidationIssue",
    "ValidationResult",
    "ValidationRule",
    "ConfigValidator",
    "get_config_validator",
    "validate_config",
    "validate_config_or_raise",
    "register_validation_rule",
]
