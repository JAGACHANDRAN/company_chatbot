from fastapi import APIRouter, HTTPException, Depends, status
from ..schemas import LoginRequest, LoginResponse, UserResponse
from ..services.auth import (
    authenticate_user,
    create_access_token,
    get_current_user
)

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """
    Authenticates an authorized user and issues a signed JWT access token.
    Only authorized uploaders configured in .env or the database can sign in.
    Details are stored in MongoDB (uploaders or users collection) upon successful login.
    """
    user_info = authenticate_user(credentials.email, credentials.password)

    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Only authorized uploaders can sign in."
        )

    user_id = user_info.get("user_id", "")
    email = user_info.get("email", "")
    role = user_info.get("role", "CHAT_USER")

    # Mint JWT containing trusted role claim
    access_token = create_access_token({
        "sub": user_id,
        "email": email,
        "role": role
    })

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            user_id=user_id,
            email=email,
            role=role
        )
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user)
):
    """
    Returns the authenticated user profile and trusted role from the backend.
    """
    return UserResponse(
        user_id=current_user["user_id"],
        email=current_user["email"],
        role=current_user["role"]
    )


@router.post("/logout")
async def logout():
    """Client-side token invalidation acknowledgment."""
    return {"success": True, "message": "Logged out successfully."}
