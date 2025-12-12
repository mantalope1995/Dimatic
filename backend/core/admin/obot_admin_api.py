from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
import httpx
import logging
from typing import Optional
import os

from core.auth import require_admin
from core.obot.audit import MCPAuditLog
from core.utils.logger import logger

router = APIRouter(
    prefix="/admin/obot",
    tags=["admin", "obot"],
    dependencies=[Depends(require_admin)]
)

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_obot_request(
    request: Request,
    path: str,
    admin: dict = Depends(require_admin)
):
    """
    Proxy requests to the Obot service for admin access.
    Only accessible by admins.
    """
    # Get Obot base URL from env
    base_url = os.getenv("OBOT_BASE_URL", "http://obot:8080/api")
    # For the admin GUI, it might be served from root or a specific path. 
    # The requirement says "Add /admin/obot/* proxy route for Admin GUI access".
    # Assuming OBOT_BASE_URL points to the API. 
    # If the GUI is part of the same service, we might need to adjust the URL construction.
    # However, for now, let's assume we proxying to the configured base URL.
    # We might need to strip /api if the base URL includes it and we want to access root.
    
    # Simple logic: If OBOT_BASE_URL ends with /api, remove it for general proxying if needed,
    # or just append the path.
    # Let's assume path is accurate.
    
    # We need to handle the case where OBOT_BASE_URL is the API url (e.g. .../api) 
    # but the GUI requires access to root resources.
    # For now, let's construct the target URL carefully.
    
    target_url = f"{base_url}/{path}"
    # If the path is empty, it might be a request to the root
    if not path:
        target_url = base_url

    # Normalize URL (remove double slashes)
    # This is a basic implementation.
    
    method = request.method
    
    # Record audit log for significant operations (optional, maybe too noisy for every request)
    # Let's log only specific methods or just debug log.
    logger.debug(f"Proxying admin request: {method} {request.url.path} -> {target_url}")
    
    # Prepare headers (exclude host to avoid conflicts)
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None) # Let httpx handle content length
    
    # Audit log for write operations
    if method in ["POST", "PUT", "DELETE", "PATCH"]:
        audit_log = MCPAuditLog()
        await audit_log.record(
            action="admin_proxy_access",
            user_id=admin.get("user_id", "unknown"),
            success=True,
            additional_context={
                "method": method,
                "path": path,
                "target_url": target_url
            }
        )

    try:
        # Use a client to forward the request
        async with httpx.AsyncClient() as client:
            # We need to read the body
            body = await request.body()
            
            proxy_req = client.build_request(
                method,
                target_url,
                headers=headers,
                content=body,
                params=request.query_params
            )
            
            response = await client.send(proxy_req, stream=True)
            
            return StreamingResponse(
                response.aiter_raw(),
                status_code=response.status_code,
                headers=dict(response.headers),
                background=None
            )
            
    except Exception as e:
        logger.error(f"Failed to proxy to Obot: {e}")
        # Record failure audit log
        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            audit_log = MCPAuditLog()
            await audit_log.record(
                action="admin_proxy_access",
                user_id=admin.get("user_id", "unknown"),
                success=False,
                error_message=str(e),
                additional_context={
                    "method": method,
                    "path": path
                }
            )
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")
