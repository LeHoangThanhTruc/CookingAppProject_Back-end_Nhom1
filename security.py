import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer_scheme = HTTPBearer(auto_error=False)


def _authentication_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error("Thiếu access token")

    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET_KEY chưa được cấu hình",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(payload["sub"])
        if user_id <= 0:
            raise ValueError
    except jwt.ExpiredSignatureError as exc:
        raise _authentication_error("Access token đã hết hạn") from exc
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise _authentication_error("Access token không hợp lệ") from exc

    return user_id
