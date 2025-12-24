"""
AgentCore Alerting Service (Phase 9)

SNS/SES-based alerting for AgentCore operations in ap-southeast-2.

Phase 9: All alerting operations use ap-southeast-2 (Australia) region for
data residency compliance.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import formataddr
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..config import AgentCoreConfig, get_config
from ..errors import (
    AgentCoreError,
    safe_log,
)

logger = logging.getLogger(__name__)

# Phase 9 required region
PHASE_9_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    """Alert delivery channels."""
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    SNS = "sns"


@dataclass
class AlertRecipient:
    """
    Alert recipient configuration.

    Attributes:
        channel: Delivery channel
        address: Email address, phone number, or webhook URL
        severity_filter: Minimum severity to send (default: INFO)
    """
    channel: AlertChannel
    address: str
    severity_filter: AlertSeverity = AlertSeverity.INFO

    def should_receive(self, severity: AlertSeverity) -> bool:
        """Check if recipient should receive alert based on severity."""
        severity_order = {
            AlertSeverity.INFO: 0,
            AlertSeverity.WARNING: 1,
            AlertSeverity.ERROR: 2,
            AlertSeverity.CRITICAL: 3,
        }
        return severity_order[severity] >= severity_order[self.severity_filter]


@dataclass
class Alert:
    """
    Alert notification.

    Attributes:
        alert_id: Unique alert identifier
        severity: Alert severity level
        title: Alert title
        message: Alert message body
        metadata: Additional metadata
        timestamp: When the alert was created
        account_id: Associated account ID
        region: Region where the alert originated
    """
    alert_id: str
    severity: AlertSeverity
    title: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    account_id: Optional[str] = None
    region: str = PHASE_9_REGION

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "account_id": self.account_id,
            "region": self.region,
        }


@dataclass
class AlertRule:
    """
    Alert rule configuration.

    Attributes:
        rule_id: Unique rule identifier
        name: Rule name
        description: Rule description
        metric_name: CloudWatch metric to monitor
        threshold: Alert threshold value
        comparison: Comparison operator (gt, lt, eq)
        severity: Alert severity when triggered
        recipients: List of recipients to notify
        enabled: Whether rule is enabled
        cooldown_seconds: Minimum seconds between alerts
    """
    rule_id: str
    name: str
    description: str
    metric_name: str
    threshold: float
    comparison: str  # "gt", "lt", "eq"
    severity: AlertSeverity
    recipients: List[AlertRecipient] = field(default_factory=list)
    enabled: bool = True
    cooldown_seconds: int = 300

    # Internal state
    _last_triggered: Optional[datetime] = field(default=None, init=False, repr=False)

    def should_trigger(self, value: float) -> bool:
        """Check if rule should trigger based on metric value."""
        if not self.enabled:
            return False

        if self.comparison == "gt":
            return value > self.threshold
        elif self.comparison == "lt":
            return value < self.threshold
        elif self.comparison == "eq":
            return value == self.threshold
        return False

    def can_trigger_now(self) -> bool:
        """Check if rule can trigger (cooldown period passed)."""
        if self._last_triggered is None:
            return True

        elapsed = (datetime.utcnow() - self._last_triggered).total_seconds()
        return elapsed >= self.cooldown_seconds

    def mark_triggered(self) -> None:
        """Mark rule as triggered."""
        self._last_triggered = datetime.utcnow()


# ============================================================================
# Alerting Service
# ============================================================================

class AlertingService:
    """
    Alerting service for AgentCore operations.

    Features:
    - Multi-channel delivery (Email, SMS, Webhook, SNS)
    - Severity-based filtering
    - Alert rules with thresholds
    - Cooldown periods to prevent spam
    - SNS/SES integration in ap-southeast-2

    Usage:
        ```python
        service = AlertingService()

        # Send alert
        await service.send_alert(Alert(
            alert_id="alert-123",
            severity=AlertSeverity.ERROR,
            title="Execution Failed",
            message="Agent execution timed out",
            account_id="account-456"
        ))

        # Create rule
        rule = AlertRule(
            rule_id="rule-123",
            name="High Error Rate",
            metric_name="ErrorRate",
            threshold=0.05,
            comparison="gt",
            severity=AlertSeverity.WARNING
        )
        await service.evaluate_rule(rule, current_value=0.08)
        ```
    """

    # Phase 9 required SNS topic prefixes
    SNS_TOPIC_PREFIX = "agentcore-alerts"

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
    ):
        """
        Initialize the alerting service.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            AgentCoreError: If config is invalid for alerting operations.
        """
        self.config = config or get_config()
        self._sns_client = None
        self._ses_client = None
        self._active_rules: Dict[str, AlertRule] = {}

        # Validate region compliance for Phase 9
        if self.config.aws_region != PHASE_9_REGION:
            safe_log(
                f"Alerting: Region '{self.config.aws_region}' specified, "
                f"but Phase 9 requires '{PHASE_9_REGION}'. "
                f"All alerts will be sent to {PHASE_9_REGION} for compliance."
            )

        safe_log("AlertingService initialized")

    def _get_sns_client(self):
        """Lazy initialization of boto3 SNS client."""
        if self._sns_client is None:
            import boto3

            self._sns_client = boto3.client(
                "sns",
                region_name=PHASE_9_REGION,  # Force ap-southeast-2 for Phase 9
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key,
            )

        return self._sns_client

    def _get_ses_client(self):
        """Lazy initialization of boto3 SES client."""
        if self._ses_client is None:
            import boto3

            self._ses_client = boto3.client(
                "ses",
                region_name=PHASE_9_REGION,  # Force ap-southeast-2 for Phase 9
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key,
            )

        return self._ses_client

    async def send_alert(
        self,
        alert: Alert,
        recipients: Optional[List[AlertRecipient]] = None,
    ) -> bool:
        """
        Send an alert to configured recipients.

        Args:
            alert: Alert to send
            recipients: Optional list of recipients (defaults to rule recipients)

        Returns:
            True if alert was sent successfully

        Raises:
            AgentCoreError: If alert sending fails
        """
        try:
            # Use provided recipients or look up from alert rules
            target_recipients = recipients or self._get_recipients_for_alert(alert)

            if not target_recipients:
                safe_log(f"No recipients configured for alert '{alert.alert_id}'")
                return True

            # Filter by severity
            filtered_recipients = [
                r for r in target_recipients
                if r.should_receive(alert.severity)
            ]

            if not filtered_recipients:
                safe_log(f"No recipients eligible for alert '{alert.alert_id}' with severity {alert.severity.value}")
                return True

            # Send to each recipient
            tasks = [
                self._send_to_recipient(alert, recipient)
                for recipient in filtered_recipients
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for failures
            failures = [r for r in results if isinstance(r, Exception)]
            if failures:
                safe_log(
                    f"Alert '{alert.alert_id}' had {len(failures)} delivery failures",
                    level="warning"
                )

            safe_log(f"Sent alert '{alert.alert_id}' to {len(filtered_recipients)} recipients")
            return True

        except Exception as e:
            safe_log(f"Failed to send alert '{alert.alert_id}': {e}", level="error")
            raise AgentCoreError(f"Failed to send alert: {e}") from e

    async def _send_to_recipient(
        self,
        alert: Alert,
        recipient: AlertRecipient,
    ) -> bool:
        """Send alert to a specific recipient."""
        try:
            if recipient.channel == AlertChannel.EMAIL:
                return await self._send_email_alert(alert, recipient.address)
            elif recipient.channel == AlertChannel.SMS:
                return await self._send_sms_alert(alert, recipient.address)
            elif recipient.channel == AlertChannel.WEBHOOK:
                return await self._send_webhook_alert(alert, recipient.address)
            elif recipient.channel == AlertChannel.SNS:
                return await self._send_sns_alert(alert, recipient.address)
            else:
                safe_log(f"Unsupported channel: {recipient.channel}", level="warning")
                return False

        except Exception as e:
            safe_log(f"Failed to send alert to {recipient.address}: {e}", level="error")
            return False

    async def _send_email_alert(
        self,
        alert: Alert,
        email_address: str,
    ) -> bool:
        """Send alert via email (SES)."""
        try:
            client = self._get_ses_client()

            # Build email subject
            subject = f"[{alert.severity.value.upper()}] {alert.title}"

            # Build email body
            body = self._format_alert_body(alert)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.send_email(
                    Source=self.config.alert_sender_email or "noreply@kortix.ai",
                    Destination={"ToAddresses": [email_address]},
                    Message={
                        "Subject": {"Data": subject},
                        "Body": {"Text": {"Data": body}},
                    },
                )
            )

            return True

        except Exception as e:
            safe_log(f"Failed to send email alert: {e}", level="error")
            return False

    async def _send_sms_alert(
        self,
        alert: Alert,
        phone_number: str,
    ) -> bool:
        """Send alert via SMS (SNS)."""
        try:
            client = self._get_sns_client()

            # Build SMS message
            message = f"[{alert.severity.value.upper()}] {alert.title}: {alert.message}"

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.publish(
                    PhoneNumber=phone_number,
                    Message=message[:160],  # SMS limit
                )
            )

            return True

        except Exception as e:
            safe_log(f"Failed to send SMS alert: {e}", level="error")
            return False

    async def _send_webhook_alert(
        self,
        alert: Alert,
        webhook_url: str,
    ) -> bool:
        """Send alert via webhook (HTTP POST)."""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=alert.to_dict(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200

        except Exception as e:
            safe_log(f"Failed to send webhook alert: {e}", level="error")
            return False

    async def _send_sns_alert(
        self,
        alert: Alert,
        topic_arn: str,
    ) -> bool:
        """Send alert via SNS topic."""
        try:
            client = self._get_sns_client()

            # Build message
            message = self._format_alert_body(alert)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.publish(
                    TopicArn=topic_arn,
                    Message=message,
                    Subject=f"[{alert.severity.value.upper()}] {alert.title}",
                )
            )

            return True

        except Exception as e:
            safe_log(f"Failed to send SNS alert: {e}", level="error")
            return False

    def _format_alert_body(self, alert: Alert) -> str:
        """Format alert body for email/SNS."""
        lines = [
            f"Alert: {alert.title}",
            f"Severity: {alert.severity.value.upper()}",
            f"Time: {alert.timestamp.isoformat()}",
            f"Region: {alert.region}",
            "",
            alert.message,
        ]

        if alert.metadata:
            lines.extend([
                "",
                "Metadata:",
            ])
            for key, value in alert.metadata.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    def _get_recipients_for_alert(self, alert: Alert) -> List[AlertRecipient]:
        """Get recipients for an alert based on configured rules."""
        # In production, this would look up recipients from a database
        # For now, return empty list (recipients must be specified explicitly)
        return []

    async def register_rule(self, rule: AlertRule) -> bool:
        """
        Register an alert rule.

        Args:
            rule: Alert rule to register

        Returns:
            True if rule was registered successfully
        """
        self._active_rules[rule.rule_id] = rule
        safe_log(f"Registered alert rule '{rule.rule_id}': {rule.name}")
        return True

    async def unregister_rule(self, rule_id: str) -> bool:
        """
        Unregister an alert rule.

        Args:
            rule_id: Rule ID to unregister

        Returns:
            True if rule was unregistered successfully
        """
        if rule_id in self._active_rules:
            del self._active_rules[rule_id]
            safe_log(f"Unregistered alert rule '{rule_id}'")
            return True
        return False

    async def evaluate_rule(
        self,
        rule: AlertRule,
        current_value: float,
        account_id: Optional[str] = None,
    ) -> bool:
        """
        Evaluate an alert rule and trigger if threshold met.

        Args:
            rule: Alert rule to evaluate
            current_value: Current metric value
            account_id: Optional account ID for context

        Returns:
            True if alert was triggered
        """
        if not rule.should_trigger(current_value):
            return False

        if not rule.can_trigger_now():
            safe_log(f"Rule '{rule.rule_id}' triggered but in cooldown period")
            return False

        # Create and send alert
        alert = Alert(
            alert_id=f"{rule.rule_id}-{datetime.utcnow().timestamp()}",
            severity=rule.severity,
            title=rule.name,
            message=f"Metric '{rule.metric_name}' is {current_value}, threshold is {rule.threshold}",
            metadata={
                "rule_id": rule.rule_id,
                "metric_name": rule.metric_name,
                "current_value": current_value,
                "threshold": rule.threshold,
            },
            account_id=account_id,
        )

        await self.send_alert(alert, recipients=rule.recipients)
        rule.mark_triggered()

        return True

    async def get_active_rules(self) -> List[AlertRule]:
        """
        Get list of active alert rules.

        Returns:
            List of active rules
        """
        return list(self._active_rules.values())


# ============================================================================
# Predefined Alert Rules
# ============================================================================

class DefaultAlertRules:
    """Default alert rule configurations."""

    @staticmethod
    def high_error_rate() -> AlertRule:
        """Alert when error rate exceeds 5%."""
        return AlertRule(
            rule_id="default-high-error-rate",
            name="High Error Rate",
            description="Alert when error rate exceeds 5%",
            metric_name="ErrorRate",
            threshold=0.05,
            comparison="gt",
            severity=AlertSeverity.WARNING,
        )

    @staticmethod
    def critical_error_rate() -> AlertRule:
        """Alert when error rate exceeds 20%."""
        return AlertRule(
            rule_id="default-critical-error-rate",
            name="Critical Error Rate",
            description="Alert when error rate exceeds 20%",
            metric_name="ErrorRate",
            threshold=0.20,
            comparison="gt",
            severity=AlertSeverity.CRITICAL,
        )

    @staticmethod
    def high_latency() -> AlertRule:
        """Alert when execution latency exceeds 30 seconds."""
        return AlertRule(
            rule_id="default-high-latency",
            name="High Execution Latency",
            description="Alert when execution latency exceeds 30 seconds",
            metric_name="ExecutionDuration",
            threshold=30000,
            comparison="gt",
            severity=AlertSeverity.WARNING,
        )

    @staticmethod
    def low_credit_balance() -> AlertRule:
        """Alert when credit balance falls below 100."""
        return AlertRule(
            rule_id="default-low-credits",
            name="Low Credit Balance",
            description="Alert when credit balance falls below 100",
            metric_name="CreditBalance",
            threshold=100,
            comparison="lt",
            severity=AlertSeverity.WARNING,
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def get_alerting_service(config: Optional[AgentCoreConfig] = None) -> AlertingService:
    """
    Get the alerting service instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        AlertingService instance
    """
    return AlertingService(config=config)


async def send_alert(
    severity: AlertSeverity,
    title: str,
    message: str,
    account_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[AgentCoreConfig] = None,
) -> bool:
    """
    Convenience function to send an alert.

    Args:
        severity: Alert severity level
        title: Alert title
        message: Alert message
        account_id: Optional tenant account ID
        metadata: Optional metadata
        config: Optional AgentCore configuration

    Returns:
        True if alert was sent successfully
    """
    import uuid

    service = get_alerting_service(config)

    alert = Alert(
        alert_id=str(uuid.uuid4()),
        severity=severity,
        title=title,
        message=message,
        metadata=metadata or {},
        account_id=account_id,
    )

    return await service.send_alert(alert)


# Export public symbols
__all__ = [
    "PHASE_9_REGION",
    "AlertSeverity",
    "AlertChannel",
    "AlertRecipient",
    "Alert",
    "AlertRule",
    "AlertingService",
    "DefaultAlertRules",
    "get_alerting_service",
    "send_alert",
]
