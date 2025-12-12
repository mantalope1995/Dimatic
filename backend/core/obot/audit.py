"""MCP Audit Logging Service

Records audit log entries for MCP operations including server creation, deletion,
tool calls, and OAuth operations for compliance and security monitoring.
"""

import os
import json
import ipaddress
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union
from uuid import uuid4

from core.services.supabase import DBConnection
from core.utils.logger import logger


class MCPAuditLog:
    """Manages audit logging for MCP operations"""
    
    def __init__(self, db_connection: Optional[DBConnection] = None):
        """
        Initialize the audit log service
        
        Args:
            db_connection: Optional database connection (uses default if not provided)
        """
        self.db = db_connection or DBConnection()
        self._enable_ip_logging = os.getenv('OBOT_ENABLE_IP_LOGGING', 'true').lower() == 'true'
        self._enable_user_agent_logging = os.getenv('OBOT_ENABLE_USER_AGENT_LOGGING', 'true').lower() == 'true'
        self._max_error_message_length = int(os.getenv('OBOT_MAX_ERROR_MESSAGE_LENGTH', '1000'))
    
    def _sanitize_ip_address(self, ip_address: Optional[str]) -> Optional[str]:
        """
        Sanitize and validate IP address for privacy compliance
        
        Args:
            ip_address: Raw IP address string
            
        Returns:
            Sanitized IP address or None if invalid
        """
        if not ip_address or not self._enable_ip_logging:
            return None
            
        try:
            # Basic IP validation
            ip = ipaddress.ip_address(ip_address.strip())
            
            # Mask last octet for IPv4 or last 5 bits for IPv6 for privacy
            if ip.version == 4:
                parts = str(ip).split('.')
                if len(parts) == 4:
                    # Mask last octet (e.g., 192.168.1.XXX -> 192.168.1.0)
                    return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
            else:
                # For IPv6, return a masked version
                return f"{str(ip)[:19]}::"  # Keep first 4 hextets only
                
            return str(ip)
        except Exception:
            # Invalid IP format, return None
            return None
    
    def _sanitize_user_agent(self, user_agent: Optional[str]) -> Optional[str]:
        """
        Sanitize user agent string for privacy compliance
        
        Args:
            user_agent: Raw user agent string
            
        Returns:
            Sanitized user agent or None if too long or disabled
        """
        if not user_agent or not self._enable_user_agent_logging:
            return None
            
        # Limit length for storage efficiency and privacy
        sanitized = user_agent.strip()[:500]
        return sanitized if sanitized else None
    
    def _sanitize_error_message(self, error_message: Optional[str]) -> Optional[str]:
        """
        Sanitize error message to prevent sensitive data leakage
        
        Args:
            error_message: Raw error message
            
        Returns:
            Sanitized error message or None
        """
        if not error_message:
            return None
            
        # Limit length and remove potential sensitive patterns
        sanitized = error_message.strip()
        
        # Truncate if too long
        if len(sanitized) > self._max_error_message_length:
            sanitized = sanitized[:self._max_error_message_length] + "..."
        
        # Basic sanitization for potential sensitive data
        # This is a simple implementation - in production, consider more sophisticated PII detection
        sensitive_patterns = [
            ('password=', '[PASSWORD_REDACTED]'),
            ('token=', '[TOKEN_REDACTED]'),
            ('api_key=', '[API_KEY_REDACTED]'),
            ('secret=', '[SECRET_REDACTED]'),
        ]
        
        for pattern, replacement in sensitive_patterns:
            if pattern in sanitized.lower():
                # Simple replacement - production should use more sophisticated parsing
                sanitized = sanitized.replace(pattern.split('=')[0] + '=', replacement)
        
        return sanitized if sanitized else None
    
    async def _insert_audit_log(
        self,
        user_id: str,
        action: str,
        server_id: Optional[str],
        tool_name: Optional[str],
        success: bool,
        error_message: Optional[str],
        ip_address: Optional[str],
        user_agent: Optional[str]
    ) -> None:
        """
        Insert audit log entry into database
        
        Args:
            user_id: Suna user UUID
            action: Operation type
            server_id: Obot server ID (optional)
            tool_name: MCP tool name (optional)
            success: Operation success status
            error_message: Error message if any (optional)
            ip_address: Client IP address (optional)
            user_agent: Client user agent (optional)
        """
        try:
            # Sanitize inputs for privacy and security
            sanitized_ip = self._sanitize_ip_address(ip_address)
            sanitized_user_agent = self._sanitize_user_agent(user_agent)
            sanitized_error = self._sanitize_error_message(error_message)
            
            # Generate audit log entry
            audit_id = str(uuid4())
            now = datetime.now(timezone.utc)
            
            # Prepare log entry data
            log_data = {
                'id': audit_id,
                'user_id': user_id,
                'action': action,
                'server_id': server_id,
                'tool_name': tool_name,
                'success': success,
                'error_message': sanitized_error,
                'ip_address': sanitized_ip,
                'user_agent': sanitized_user_agent,
                'created_at': now.isoformat()
            }
            
            # Insert into database
            client = await self.db.client
            result = await client.table('obot_audit_logs').insert(log_data).execute()
            
            if not result.data:
                raise Exception("Failed to insert audit log entry")
            
            # Log success (debug level to avoid noise in production)
            logger.debug(f"Audit log recorded: {action} by {user_id[:8]}... (success: {success})")
            
        except Exception as e:
            # Don't let audit logging failures break the main operation
            logger.error(f"Failed to record audit log: {e}", exc_info=True)
    
    async def record(
        self,
        action: str,
        user_id: str,
        success: bool = True,
        server_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record an audit log entry for an MCP operation
        
        Args:
            action: Operation type ('server_create', 'server_delete', 'tool_call', 'oauth_start')
            user_id: Suna user UUID making the request
            success: Whether the operation succeeded
            server_id: Obot server ID (optional)
            tool_name: MCP tool name that was called (optional)
            error_message: Error message if operation failed (optional)
            ip_address: Client IP address from request context (optional)
            user_agent: Client user agent from request context (optional)
            additional_context: Additional context data as JSON (optional)
        """
        try:
            # Validate action type
            valid_actions = {'server_create', 'server_delete', 'tool_call', 'oauth_start', 'server_update'}
            if action not in valid_actions:
                logger.warning(f"Invalid audit action: {action}")
                action = 'unknown_action'
            
            # Validate user_id format (basic UUID check)
            if not user_id or len(user_id) < 8:
                logger.error(f"Invalid user_id for audit log: {user_id}")
                return
            
            # Log the audit event
            await self._insert_audit_log(
                user_id=user_id,
                action=action,
                server_id=server_id,
                tool_name=tool_name,
                success=success,
                error_message=error_message,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
        except Exception as e:
            # Don't let audit logging failures break the main operation
            logger.error(f"Failed to record audit log for {action}: {e}", exc_info=True)
    
    async def record_server_operation(
        self,
        operation: str,
        user_id: str,
        server_id: str,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """
        Convenience method to record server operations
        
        Args:
            operation: Server operation type ('create', 'delete', 'update')
            user_id: Suna user UUID
            server_id: Obot server ID
            success: Operation success status
            error_message: Error message if failed (optional)
            ip_address: Client IP address (optional)
            user_agent: Client user agent (optional)
        """
        action_map = {
            'create': 'server_create',
            'delete': 'server_delete', 
            'update': 'server_update'
        }
        
        action = action_map.get(operation.lower(), 'server_operation')
        
        await self.record(
            action=action,
            user_id=user_id,
            success=success,
            server_id=server_id,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    async def record_tool_call(
        self,
        user_id: str,
        server_id: str,
        tool_name: str,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """
        Convenience method to record tool call operations
        
        Args:
            user_id: Suna user UUID
            server_id: Obot server ID
            tool_name: MCP tool name that was called
            success: Tool execution success status
            error_message: Error message if failed (optional)
            ip_address: Client IP address (optional)
            user_agent: Client user agent (optional)
        """
        await self.record(
            action='tool_call',
            user_id=user_id,
            success=success,
            server_id=server_id,
            tool_name=tool_name,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    async def record_oauth_operation(
        self,
        operation: str,
        user_id: str,
        server_id: str,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """
        Convenience method to record OAuth operations
        
        Args:
            operation: OAuth operation type ('start', 'callback', 'refresh')
            user_id: Suna user UUID
            server_id: Obot server ID
            success: OAuth operation success status
            error_message: Error message if failed (optional)
            ip_address: Client IP address (optional)
            user_agent: Client user agent (optional)
        """
        # For now, all OAuth operations are recorded as 'oauth_start'
        # In a more sophisticated implementation, we could distinguish between types
        await self.record(
            action='oauth_start',
            user_id=user_id,
            success=success,
            server_id=server_id,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    async def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        server_id: Optional[str] = None,
        action: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs with filtering options
        
        Args:
            user_id: Filter by user ID (optional)
            server_id: Filter by server ID (optional)
            action: Filter by action type (optional)
            success: Filter by success status (optional)
            limit: Maximum number of records to return (default: 100)
            offset: Number of records to skip (default: 0)
            start_date: Filter records after this date (optional)
            end_date: Filter records before this date (optional)
            
        Returns:
            List of audit log entries as dictionaries
            
        Raises:
            Exception: If database query fails
        """
        try:
            logger.debug(f"Retrieving audit logs with filters: user_id={user_id}, server_id={server_id}, action={action}")
            
            client = await self.db.client
            query = client.table('obot_audit_logs').select('*')
            
            # Apply filters
            if user_id:
                query = query.eq('user_id', user_id)
            if server_id:
                query = query.eq('server_id', server_id)
            if action:
                query = query.eq('action', action)
            if success is not None:
                query = query.eq('success', success)
            if start_date:
                query = query.gte('created_at', start_date.isoformat())
            if end_date:
                query = query.lte('created_at', end_date.isoformat())
            
            # Apply ordering and pagination
            result = query.order('created_at', desc=True).range(offset, offset + limit - 1).execute()
            
            if not result.data:
                logger.debug("No audit logs found matching the criteria")
                return []
            
            logs = result.data
            logger.debug(f"Retrieved {len(logs)} audit log entries")
            return logs
            
        except Exception as e:
            logger.error(f"Failed to retrieve audit logs: {e}", exc_info=True)
            raise
    
    async def get_user_audit_summary(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get audit summary statistics for a user
        
        Args:
            user_id: User ID to get summary for
            days: Number of days to look back (default: 30)
            
        Returns:
            Dictionary with audit summary statistics
            
        Raises:
            Exception: If database query fails
        """
        try:
            logger.debug(f"Getting audit summary for user {user_id} over {days} days")
            
            client = await self.db.client
            start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = start_date.replace(day=start_date.day - days)
            
            # Get total count
            total_result = await client.table('obot_audit_logs').select('id', count='exact').eq(
                'user_id', user_id
            ).gte('created_at', start_date.isoformat()).execute()
            
            # Get success/failure counts
            success_result = await client.table('obot_audit_logs').select('id', count='exact').eq(
                'user_id', user_id
            ).eq('success', True).gte('created_at', start_date.isoformat()).execute()
            
            failure_result = await client.table('obot_audit_logs').select('id', count='exact').eq(
                'user_id', user_id
            ).eq('success', False).gte('created_at', start_date.isoformat()).execute()
            
            # Get action breakdown
            action_result = await client.table('obot_audit_logs').select('action').eq(
                'user_id', user_id
            ).gte('created_at', start_date.isoformat()).execute()
            
            # Process action counts
            action_counts = {}
            if action_result.data:
                for entry in action_result.data:
                    action = entry['action']
                    action_counts[action] = action_counts.get(action, 0) + 1
            
            # Calculate summary
            total_count = total_result.count or 0
            success_count = success_result.count or 0
            failure_count = failure_result.count or 0
            
            summary = {
                'user_id': user_id,
                'period_days': days,
                'total_operations': total_count,
                'successful_operations': success_count,
                'failed_operations': failure_count,
                'success_rate': round((success_count / total_count * 100), 2) if total_count > 0 else 0,
                'action_breakdown': action_counts,
                'period_start': start_date.isoformat(),
                'period_end': datetime.now(timezone.utc).isoformat()
            }
            
            logger.debug(f"Audit summary for user {user_id}: {summary['total_operations']} total operations")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get audit summary for user {user_id}: {e}", exc_info=True)
            raise
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Check the health of the audit logging system
        
        Returns:
            Dictionary with health check results
        """
        try:
            # Test database connectivity
            client = await self.db.client
            result = await client.table('obot_audit_logs').select('id').limit(1).execute()
            
            # Check if we can write a test log entry
            test_user_id = "health-check-user"
            test_action = "health_check"
            
            await self.record(
                action=test_action,
                user_id=test_user_id,
                success=True,
                server_id="health-check-server"
            )
            
            # Clean up test entry
            await client.table('obot_audit_logs').delete().eq('user_id', test_user_id).eq(
                'action', test_action
            ).execute()
            
            return {
                'status': 'healthy',
                'database_connected': True,
                'can_write_logs': True,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Audit log health check failed: {e}")
            return {
                'status': 'unhealthy',
                'database_connected': False,
                'can_write_logs': False,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
