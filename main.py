import os
from typing import Optional
from fastapi import FastAPI, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models
from auth import get_token_from_request, SECRET_KEY, ALGORITHM
import jwt

# テーブル自動生成
Base.metadata.create_all(bind=engine)

# 初期データ投入
try:
    import seed
    seed.seed_data()
except Exception as e:
    print(f"seed error: {e}")

app = FastAPI(
    title="薬局スタッフプラットフォーム",
    version="2.0.0",
)

# 静的ファイル・テンプレート
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ルーター登録
from routers import auth_router, calendar_router, me_router, admin_router
app.include_router(auth_router)
app.include_router(calendar_router)
app.include_router(me_router)
app.include_router(admin_router)


def get_current_user_optional(request: Request, db: Session) -> Optional[models.User]:
    token = get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            return None
        return db.query(models.User).filter(
            models.User.id == user_id,
            models.User.is_active == True
        ).first()
    except Exception:
        return None


# --- HTMLページルート ---

@app.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db)):
    """トップ → カレンダー（ログイン不要で見られる）"""
    return RedirectResponse(url="/calendar", status_code=302)


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request, db: Session = Depends(get_db)):
    """公開シフトカレンダー（ログイン不要）"""
    user = get_current_user_optional(request, db)
    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={"current_user": user}
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    """三重ロックログイン画面"""
    user = get_current_user_optional(request, db)
    if user:
        if user.is_admin:
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/me", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@app.get("/me", response_class=HTMLResponse)
def myroom_page(request: Request, db: Session = Depends(get_db)):
    """マイルーム（ログイン必須・本人のみ）"""
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.is_admin:
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="myroom.html",
        context={"current_user": user}
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    """管理者ダッシュボード（管理者のみ）"""
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.is_admin:
        return RedirectResponse(url="/me", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"current_user": user}
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": "2.0.0"}
