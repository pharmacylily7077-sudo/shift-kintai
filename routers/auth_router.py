from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
import models
from auth import verify_password, create_access_token, get_token_from_request, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
import jwt

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    position: str   # PHARMACIST / CLERK / ASSISTANT
    username: str   # 三宅 / 家田 etc（フルネーム）
    password: str


@router.get("/staff-list")
def get_staff_list(position: str, db: Session = Depends(get_db)):
    """
    三重ロックSTEP2: ポジションを選ぶとそのポジションの名前一覧を返す
    """
    try:
        pos = models.Position(position)
    except ValueError:
        raise HTTPException(status_code=400, detail="無効なポジションです")

    users = db.query(models.User).filter(
        models.User.position == pos,
        models.User.is_active == True
    ).order_by(models.User.id).all()

    return [
        {
            "username": u.username,
            "full_name": u.full_name,
            "evaluation_color": u.evaluation_color,
            "position": u.position.value,
        }
        for u in users
    ]


@router.post("/login")
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """
    三重ロックSTEP3: ポジション+ユーザー名+パスワードで認証
    """
    # ポジション確認
    try:
        pos = models.Position(data.position)
    except ValueError:
        raise HTTPException(status_code=401, detail="認証に失敗しました")

    # ユーザー検索（ポジション+username の組み合わせ）
    user = db.query(models.User).filter(
        models.User.username == data.username,
        models.User.position == pos,
        models.User.is_active == True
    ).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="認証に失敗しました")

    token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "is_admin": user.is_admin}
    )

    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        samesite="lax",
        max_age=60 * ACCESS_TOKEN_EXPIRE_MINUTES,
        path="/"
    )

    return {
        "success": True,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "position": user.position.value,
        "theme_color": user.theme_color,
        "theme_bg": user.theme_bg,
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"success": True}


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="未ログイン")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        user = db.query(models.User).filter(
            models.User.id == user_id,
            models.User.is_active == True
        ).first()
        if not user:
            raise HTTPException(status_code=401, detail="ユーザーが見つかりません")
        return {
            "id": user.id,
            "full_name": user.full_name,
            "position": user.position.value,
            "position_label": user.position_label,
            "employment_type": user.employment_type.value,
            "is_admin": user.is_admin,
            "theme_color": user.theme_color,
            "theme_bg": user.theme_bg,
            "color": user.position_color,
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="セッション期限切れ")
    except Exception:
        raise HTTPException(status_code=401, detail="認証エラー")
