import os
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models
from routers import auth, staff, admin
from auth import get_token_from_request, SECRET_KEY, ALGORITHM
import jwt

# テーブル自動生成
Base.metadata.create_all(bind=engine)

# 初期データ自動投入（未初期化時のみ）
try:
    import seed
    seed.seed_data()
except Exception:
    pass

app = FastAPI(
    title="薬局シフト勤怠・個人給与シミュレータ＆有休管理",
    description="セキュア・高速・堅牢な薬局向け勤怠・シフト・給与管理システム",
    version="1.0.0"
)

# 静的ファイルとテンプレート
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# APIルーター登録
app.include_router(auth.router)
app.include_router(staff.router)
app.include_router(admin.router)

def get_current_user_optional(request: Request, db: Session) -> models.User:
    token = get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            return None
        return db.query(models.User).filter(models.User.username == username, models.User.is_active == True).first()
    except Exception:
        return None

# --- HTML ページルート ---
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role == "admin":
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if user:
        if user.role == "admin":
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    active_users = db.query(models.User).filter(
        models.User.is_active == True
    ).order_by(models.User.role.asc(), models.User.id.asc()).all()
    return templates.TemplateResponse(request=request, name="login.html", context={"users": active_users})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="admin.html", context={"user": user})

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/manifest.json", include_in_schema=False)
def manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")

@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse("static/service-worker.js", media_type="application/javascript")
