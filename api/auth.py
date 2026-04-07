"""
Authentication utilities for verifying Supabase JWT tokens.
"""

import os
from typing import Optional
from fastapi import HTTPException, Header
import jwt
from jwt import PyJWKClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Supabase JWT settings
SUPABASE_URL = os.getenv("SUPABASE_URL", "")

# JWKS endpoint for ES256/RS256 token verification
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None

# Initialize JWKS client (caches keys)
jwks_client = PyJWKClient(JWKS_URL) if JWKS_URL else None


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
        # Get the signing key from JWKS endpoint
        if jwks_client:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "HS256"],
                audience="authenticated"
            )
        else:
            # Fallback: decode without verification (development only)
            print("Auth: No JWKS client, decoding without verification")
            payload = jwt.decode(token, options={"verify_signature": False})
        
        # Extract user ID from the 'sub' claim
        user_id = payload.get("sub")
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        print(f"Auth: Invalid token error: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """
    Require authentication - raises HTTPException if not authenticated.
    """
    user_id = get_user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id
