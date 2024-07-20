"""
Create, sign and verify JWT Tokens
"""

from datetime import datetime, timedelta
import json
from typing import Any, Union

from fastapi import HTTPException, status
import jwt
from jwt.exceptions import MissingRequiredClaimError

from app.auth.settings import (
    ALGORITHM,
    JWT_SECRET_DECODE_KEY,
)


DEFAULT_OPTIONS = {
    "iss": "openferp.org",
}


DEFAULT_DECODE_CONFIG = {"JWT_KEY": JWT_SECRET_DECODE_KEY, "JWT_ALGO": ALGORITHM}


class JWTValidationError(Exception):
    def __init__(self):
        super().__init__("JWTValidationError: ")


def decode_jwt_token(
    token: str,
    config: dict[str, Any] | None = None,
) -> Union[dict[str, Any], None]:
    """
    Decode a signed token with a defined algorithm and secret
    for signature. The payload is a dict and the expire time is in minutes
    """

    if config is None:
        config = DEFAULT_DECODE_CONFIG

    decoded_claims: Union[dict[str, Any], None] = None

    decoded_claims = jwt.decode(
        token,
        key=config["JWT_KEY"],
        algorithms=config["JWT_ALGO"],
        issuer=DEFAULT_OPTIONS["iss"],
    )

    if decoded_claims is None:
        raise JWTValidationError()

    print("Claims: ", str(decoded_claims))
    print("Sub: ", str(decoded_claims["sub"]))

    decoded_claims.update({"sub": json.loads(decoded_claims["sub"])})

    if abs(
        (datetime.fromtimestamp(decoded_claims["exp"]) - datetime.now())
    ) <= timedelta(0):
        raise MissingRequiredClaimError("Invalid exp time")

    return decoded_claims


def get_user_data(token: str) -> dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_jwt_token(token)

        if payload is None or payload.get("sub") is None:
            raise credentials_exception

        user_data: dict = payload.get("sub", {})

        if user_data is None:
            raise credentials_exception

    except JWTValidationError as e:
        raise credentials_exception from e

    return user_data
