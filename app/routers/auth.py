from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models import User
from app.routers.deps import SessionDep
from app.schemas.auth import AuthSessionResponse, LoginRequest, RegisterRequest
from app.schemas.user import UserRead
from app.services import auth
from app.services.errors import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


async def _require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("missing bearer token")
    return credentials.credentials


TokenDep = Annotated[str, Depends(_require_token)]


async def get_current_user(token: TokenDep, session: SessionDep) -> User:
    return await auth.resolve_session(session, token)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> AuthSessionResponse:
    user, token = await auth.register(session, payload.email, payload.password)
    return AuthSessionResponse(token=token, user=UserRead.model_validate(user))


@router.post("/login")
async def login(payload: LoginRequest, session: SessionDep) -> AuthSessionResponse:
    user, token = await auth.login(session, payload.email, payload.password)
    return AuthSessionResponse(token=token, user=UserRead.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(token: TokenDep, session: SessionDep) -> None:
    await auth.logout(session, token)


@router.get("/me")
async def me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)
