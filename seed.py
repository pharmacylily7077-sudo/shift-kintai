"""
初期スタッフデータ投入
実行のたびに既存データをチェックし、存在しない場合のみ追加する
"""
from database import SessionLocal, engine, Base
import models
from auth import hash_password

# 初期スタッフデータ（三宅薬局長による評価・成長カラー設定反映）
INITIAL_STAFF = [
    # 薬剤師（緑系統）
    {
        "full_name": "三宅 智之",
        "position": models.Position.PHARMACIST,
        "employment_type": models.EmploymentType.FULLTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "miyake",
        "password": "admin123",
        "is_admin": True,
        "evaluation_color": "#064e3b", # 黒に近い緑
        "fixed_off_weekdays": "6", # 日曜休み
    },
    {
        "full_name": "家田 知美",
        "position": models.Position.PHARMACIST,
        "employment_type": models.EmploymentType.FULLTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "ieda",
        "password": "ieda1234",
        "is_admin": False,
        "evaluation_color": "#10b981", # 綺麗な緑、エメラルドグリーン
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
    # 調剤事務（青系統）
    {
        "full_name": "寺内 美和",
        "position": models.Position.CLERK,
        "employment_type": models.EmploymentType.FULLTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "terauchi",
        "password": "terauchi1234",
        "is_admin": False,
        "evaluation_color": "#2563eb", # ロイヤルブルー
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
    {
        "full_name": "山中 久美",
        "position": models.Position.CLERK,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "yamanaka",
        "password": "yamanaka1234",
        "is_admin": False,
        "evaluation_color": "#1e3a8a", # 濃いめの青、ネイビーブルー
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
    # 調剤補助
    {
        "full_name": "小林 彩乃",
        "position": models.Position.ASSISTANT,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "kobayashi",
        "password": "kobayashi1234",
        "is_admin": False,
        "evaluation_color": "#8b5cf6", # ビビッドなバイオレット
        "fixed_off_weekdays": "3,6", # 木曜・日曜休み
    },
    {
        "full_name": "本間 まや",
        "position": models.Position.ASSISTANT,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.FULL,
        "username": "honma",
        "password": "honma1234",
        "is_admin": False,
        "evaluation_color": "#f43f5e", # 赤に近いピンク
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
    },
]


def seed_data():
    from database import init_db
    init_db()
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
                    evaluation_color=staff.get("evaluation_color"),
                    fixed_off_weekdays=staff.get("fixed_off_weekdays", "6"),
                    is_active=True,
                )
                db.add(user)
            else:
                existing.full_name = staff["full_name"]
                existing.evaluation_color = staff.get("evaluation_color")
                existing.fixed_off_weekdays = staff.get("fixed_off_weekdays", "6")
        db.commit()
        print("✅ 初期データ投入完了（評価カラー同期済み）")

        # 月間シフトが未生成の場合、今月と翌月のシフトを自動初期生成
        from datetime import date
        import calendar
        from shift_rules import calculate_shift_type

        today = date.today()
        target_months = [(today.year, today.month)]
        if today.month == 12:
            target_months.append((today.year + 1, 1))
        else:
            target_months.append((today.year, today.month + 1))

        all_users = db.query(models.User).filter(models.User.is_active == True).all()
        for y, m in target_months:
            _, days_in_month = calendar.monthrange(y, m)
            shift_count = db.query(models.Shift).filter(
                models.Shift.date >= date(y, m, 1),
                models.Shift.date <= date(y, m, days_in_month)
            ).count()
            if shift_count == 0:
                for day in range(1, days_in_month + 1):
                    d = date(y, m, day)
                    for u in all_users:
                        st = calculate_shift_type(u, d)
                        if st is not None:
                            db.add(models.Shift(user_id=u.id, date=d, shift_type=st, note=""))
                db.commit()
                print(f"✅ {y}年{m}月の初期シフト自動生成完了（スタッフカラー反映）")

        # 既存シフトに対する新ルール（土曜日全員午前診、本間木曜午前診、小林火曜午前診）の同期補正
        all_existing_shifts = db.query(models.Shift).all()
        corrected_count = 0
        for s in all_existing_shifts:
            user = db.query(models.User).filter(models.User.id == s.user_id).first()
            if not user:
                continue
            expected_st = calculate_shift_type(user, s.date)
            if expected_st and s.shift_type != expected_st:
                s.shift_type = expected_st
                corrected_count += 1
        if corrected_count > 0:
            db.commit()
            print(f"✅ 既存シフト {corrected_count}件 を新シフトルール（土曜AM・本間木曜AM・小林火曜AM）に補正完了")
    except Exception as e:
        db.rollback()
        print(f"❌ シードエラー: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
