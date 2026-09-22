"""
初期スタッフデータ投入
実行のたびに既存データをチェックし、存在しない場合のみ追加する
"""
from database import SessionLocal, engine, Base
import models
from auth import hash_password

# 初期スタッフデータ
INITIAL_STAFF = [
    # 管理者（薬剤師）
    {
        "full_name": "三宅",
        "position": models.Position.PHARMACIST,
        "employment_type": models.EmploymentType.FULLTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "miyake",
        "password": "admin123",
        "is_admin": True,
        "fixed_off_weekdays": "6", # 日曜休み
    },
    # 薬剤師
    {
        "full_name": "家田",
        "position": models.Position.PHARMACIST,
        "employment_type": models.EmploymentType.FULLTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "ieda",
        "password": "ieda1234",
        "is_admin": False,
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
    # 調剤事務
    {
        "full_name": "寺内",
        "position": models.Position.CLERK,
        "employment_type": models.EmploymentType.FULLTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "terauchi",
        "password": "terauchi1234",
        "is_admin": False,
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
    {
        "full_name": "山中",
        "position": models.Position.CLERK,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.AM,   # 午前診/午後診
        "username": "yamanaka",
        "password": "yamanaka1234",
        "is_admin": False,
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
    # 調剤補助
    {
        "full_name": "小林",
        "position": models.Position.ASSISTANT,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.SECOND,  # 後半
        "username": "kobayashi",
        "password": "kobayashi1234",
        "is_admin": False,
        "fixed_off_weekdays": "3,6", # 木曜・日曜休み
    },
    {
        "full_name": "本間",
        "position": models.Position.ASSISTANT,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.FIRST,   # 前半
        "username": "honma",
        "password": "honma1234",
        "is_admin": False,
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
]


def seed_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for staff in INITIAL_STAFF:
            existing = db.query(models.User).filter(
                models.User.username == staff["username"]
            ).first()
            if not existing:
                user = models.User(
                    full_name=staff["full_name"],
                    position=staff["position"],
                    employment_type=staff["employment_type"],
                    default_shift=staff["default_shift"],
                    username=staff["username"],
                    password_hash=hash_password(staff["password"]),
                    is_admin=staff["is_admin"],
                    fixed_off_weekdays=staff.get("fixed_off_weekdays", "6"),
                    is_active=True,
                )
                db.add(user)
            else:
                existing.fixed_off_weekdays = staff.get("fixed_off_weekdays", "6")
        db.commit()
        print("✅ 初期データ投入完了")
    except Exception as e:
        db.rollback()
        print(f"❌ シードエラー: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
