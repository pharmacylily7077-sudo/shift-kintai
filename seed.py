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
        "weekly_shift_pattern": '{"0":"FULL","1":"FULL","2":"FULL","3":"FULL","4":"FULL","5":"AM","6":"OFF"}',
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
        "weekly_shift_pattern": '{"0":"FULL","1":"OFF","2":"FULL","3":"FULL","4":"FULL","5":"AM","6":"OFF"}',
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
        "weekly_shift_pattern": '{"0":"FULL","1":"OFF","2":"FULL","3":"FULL","4":"FULL","5":"AM","6":"OFF"}',
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
        "weekly_shift_pattern": '{"0":"FULL","1":"OFF","2":"FULL","3":"FULL","4":"FULL","5":"AM","6":"OFF"}',
    },
    # 調剤補助
    {
        "full_name": "小林 彩乃",
        "position": models.Position.ASSISTANT,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.SECOND, # 後半 (10:00〜19:00)
        "username": "kobayashi",
        "password": "kobayashi1234",
        "is_admin": False,
        "evaluation_color": "#8b5cf6", # ビビッドなバイオレット
        "fixed_off_weekdays": "3,6", # 木曜・日曜休み
        "weekly_shift_pattern": '{"0":"SECOND","1":"FIRST","2":"SECOND","3":"OFF","4":"SECOND","5":"AM","6":"OFF"}',
    },
    {
        "full_name": "本間 まや",
        "position": models.Position.ASSISTANT,
        "employment_type": models.EmploymentType.PARTTIME,
        "default_shift": models.ShiftType.FIRST,  # 前半 (9:00〜18:00)
        "username": "honma",
        "password": "honma1234",
        "is_admin": False,
        "evaluation_color": "#f43f5e", # 赤に近いピンク
        "fixed_off_weekdays": "1,6", # 火曜・日曜休み
        "weekly_shift_pattern": '{"0":"FIRST","1":"OFF","2":"FIRST","3":"AM","4":"FIRST","5":"AM","6":"OFF"}',
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
                    weekly_shift_pattern=staff.get("weekly_shift_pattern"),
                    is_active=True,
                )
                db.add(user)
            else:
                existing.full_name = staff["full_name"]
                existing.default_shift = staff["default_shift"]
                existing.evaluation_color = staff.get("evaluation_color")
                existing.fixed_off_weekdays = staff.get("fixed_off_weekdays", "6")
                existing.weekly_shift_pattern = staff.get("weekly_shift_pattern")
        db.commit()
        print("✅ 初期データ投入完了（スタッフ個別シフト＆曜日別パターン同期済み）")

        # 確定バックアップデータ (seed_data_backup.json) の自動復元
        import os
        import json
        from datetime import date, time, datetime
        import calendar
        from shift_rules import calculate_shift_type

        backup_file = os.path.join(os.path.dirname(__file__), "seed_data_backup.json")
        if os.path.exists(backup_file):
            try:
                with open(backup_file, "r", encoding="utf-8") as f:
                    bdata = json.load(f)

                user_by_uname = {u.username: u for u in db.query(models.User).all()}

                # 1. 2026年9月シフトの復元 (未投入時のみ)
                sep_shift_count = db.query(models.Shift).filter(
                    models.Shift.date >= date(2026, 9, 1),
                    models.Shift.date <= date(2026, 9, 30)
                ).count()
                if sep_shift_count == 0 and "sep_shifts" in bdata:
                    for s_item in bdata["sep_shifts"]:
                        u = user_by_uname.get(s_item["username"])
                        if u:
                            dt = datetime.strptime(s_item["date"], "%Y-%m-%d").date()
                            st = models.ShiftType(s_item["shift_type"])
                            db.add(models.Shift(user_id=u.id, date=dt, shift_type=st, note=s_item.get("note", "")))
                    db.commit()
                    print(f"✅ 2026年9月確定シフト（{len(bdata['sep_shifts'])}件）の自動復元完了")

                # 2. 2026年10月シフトの復元 (未投入時のみ)
                oct_shift_count = db.query(models.Shift).filter(
                    models.Shift.date >= date(2026, 10, 1),
                    models.Shift.date <= date(2026, 10, 31)
                ).count()
                if oct_shift_count == 0 and "oct_shifts" in bdata:
                    for s_item in bdata["oct_shifts"]:
                        u = user_by_uname.get(s_item["username"])
                        if u:
                            dt = datetime.strptime(s_item["date"], "%Y-%m-%d").date()
                            st = models.ShiftType(s_item["shift_type"])
                            db.add(models.Shift(user_id=u.id, date=dt, shift_type=st, note=s_item.get("note", "")))
                    db.commit()
                    print(f"✅ 2026年10月確定シフト（{len(bdata['oct_shifts'])}件）の自動復元完了")

                # 3. 小林彩乃さんの2026年9月確定出勤簿の復元 (未投入時のみ)
                kobayashi = user_by_uname.get("kobayashi")
                if kobayashi and "kobayashi_records" in bdata:
                    k_sep_tc_count = db.query(models.TimeRecord).filter(
                        models.TimeRecord.user_id == kobayashi.id,
                        models.TimeRecord.date >= date(2026, 9, 1),
                        models.TimeRecord.date <= date(2026, 9, 30)
                    ).count()
                    if k_sep_tc_count == 0:
                        for tr in bdata["kobayashi_records"]:
                            dt = datetime.strptime(tr["date"], "%Y-%m-%d").date()
                            cin = datetime.strptime(tr["clock_in"][:8], "%H:%M:%S").time() if tr["clock_in"] else None
                            cout = datetime.strptime(tr["clock_out"][:8], "%H:%M:%S").time() if tr["clock_out"] else None
                            b_start = datetime.strptime(tr["break_start"][:8], "%H:%M:%S").time() if tr.get("break_start") else None
                            b_end = datetime.strptime(tr["break_end"][:8], "%H:%M:%S").time() if tr.get("break_end") else None
                            rec = models.TimeRecord(
                                user_id=kobayashi.id,
                                date=dt,
                                clock_in=cin,
                                clock_out=cout,
                                break_start=b_start,
                                break_end=b_end,
                                status=models.ClockStatus(tr.get("status", "DONE"))
                            )
                            db.add(rec)
                        db.commit()
                        print(f"✅ 小林彩乃さんの9月確定出勤簿（{len(bdata['kobayashi_records'])}日分）の自動復元完了")
            except Exception as e:
                print(f"⚠️ バックアップ自動復元エラー: {e}")

        # 月間シフトが未生成の場合、2026年9月〜12月のシフトを自動初期生成 (未作成月のみ)
        target_months = [(2026, 9), (2026, 10), (2026, 11), (2026, 12)]
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
                print(f"✅ {y}年{m}月の初期シフト自動生成完了")

        # ※ユーザーが手入力したシフトを勝手に上書き・破壊しないため、既存シフトの強制一括補正ループは廃止。

    except Exception as e:
        db.rollback()
        print(f"❌ シードエラー: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
