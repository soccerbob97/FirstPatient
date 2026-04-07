"""
Authentication utilities for verifying Supabase JWT tokens.
"""

import os
from typing import Optional
from fastapi import HTTPException, Header
import jwt
from jwt import PyJWKClient

# Supabase JWT settings
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# For RS256 tokens, we need the JWKS endpoint
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None


def get_user_id_from_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """
    Extract and verify user ID from Supabase JWT token.
    Returns None if no token provided (allows anonymous access).
    Raises HTTPException if token is invalid.
    """
    if not authorization:
        return None
    
    if not authorization.startswith("Bearer "):
        return None
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    try:
        # Supabase uses HS256 with the JWT secret
        if SUPABASE_JWT_SECRET:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated"
            )
        else:
            # Fallback: decode without verification (NOT recommended for production)
            payload = jwt.decode(token, options={"verify_signature": False})
        
        # Extract user ID from the 'sub' claim
        user_id = payload.get("sub")
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """
    Require authentication - raises HTTPException if not authenticated.
    """
    user_id = get_user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id
