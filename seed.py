import calendar
from datetime import datetime, date, time, timedelta
from database import SessionLocal, engine, Base
import models
from auth import hash_password

def seed_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 既存データの確認
        existing_admin = db.query(models.User).filter(models.User.username == "admin").first()
        if existing_admin:
            print("マスターデータは既に存在します。スキップします。")
            return

        print("初期マスターデータを作成中...")

        # 1. ユーザー作成
        admin_user = models.User(
            username="admin",
            password_hash=hash_password("admin123"),
            full_name="管理 太郎（薬局長）",
            role="admin",
            wage_type="MONTHLY",
            monthly_salary=450000,
            hourly_wage=2800,
            paid_leave_granted=15.0,
            paid_leave_carried=5.0,
            paid_leave_base_date=date(2026, 4, 1),
            work_days="0,1,2,3,4",
            default_start_time=time(9, 0),
            default_end_time=time(18, 0),
            default_break_minutes=60,
            color="#7c3aed",
            is_active=True
        )

        staff1 = models.User(
            username="staff01",
            password_hash=hash_password("staff123"),
            full_name="佐藤 健（薬剤師）",
            role="staff",
            wage_type="HOURLY",
            hourly_wage=2400,
            monthly_salary=0,
            paid_leave_granted=10.0,
            paid_leave_carried=2.0,
            paid_leave_base_date=date(2026, 4, 1),
            work_days="0,1,2,4,5",
            default_start_time=time(9, 0),
            default_end_time=time(18, 0),
            default_break_minutes=60,
            color="#059669",
            is_active=True
        )

        staff2 = models.User(
            username="staff02",
            password_hash=hash_password("staff123"),
            full_name="田中 美咲（調剤事務・パート）",
            role="staff",
            wage_type="HOURLY",
            hourly_wage=1200,
            monthly_salary=0,
            paid_leave_granted=7.0,
            paid_leave_carried=1.0,
            paid_leave_base_date=date(2026, 4, 1),
            work_days="1,3,5",
            default_start_time=time(9, 30),
            default_end_time=time(15, 30),
            default_break_minutes=60,
            color="#d97706",
            is_active=True
        )

        db.add_all([admin_user, staff1, staff2])
        db.commit()
        db.refresh(admin_user)
        db.refresh(staff1)
        db.refresh(staff2)

        today = date.today()
        current_year = today.year
        current_month = today.month

        # 2. 当月シフトデータのサンプル生成
        _, last_day = calendar.monthrange(current_year, current_month)
        
        for d_num in range(1, last_day + 1):
            d = date(current_year, current_month, d_num)
            weekday = d.weekday()  # 0: Mon, ..., 6: Sun

            # 日曜は公休
            if weekday == 6:
                continue

            # staff01 (月・火・水・金・土 勤務)
            if weekday in [0, 1, 2, 4, 5]:
                # 毎月15日は有給休暇のサンプル
                shift_type = "PAID_LEAVE" if d_num == 15 else "NORMAL"
                db.add(models.Shift(
                    user_id=staff1.id,
                    date=d,
                    start_time=time(9, 0),
                    end_time=time(18, 0),
                    break_minutes=60,
                    shift_type=shift_type,
                    note="通常シフト" if shift_type == "NORMAL" else "計画有休"
                ))

            # staff02 (火・木・土 勤務、パート)
            if weekday in [1, 3, 5]:
                db.add(models.Shift(
                    user_id=staff2.id,
                    date=d,
                    start_time=time(9, 30),
                    end_time=time(15, 30),
                    break_minutes=60,
                    shift_type="NORMAL",
                    note="扶養内調整シフト"
                ))

        db.commit()

        # 3. 過去数日間の実打刻サンプル (今月1日〜昨日まで)
        for d_num in range(1, today.day):
            d = date(current_year, current_month, d_num)
            weekday = d.weekday()

            if weekday in [0, 1, 2, 4, 5] and d_num != 15:
                # staff01 勤務実績 (8時間実働 = 480分)
                cin = datetime.combine(d, time(8, 55))
                cout = datetime.combine(d, time(18, 5))
                bstart = datetime.combine(d, time(13, 0))
                bend = datetime.combine(d, time(14, 0))
                db.add(models.TimeRecord(
                    user_id=staff1.id,
                    date=d,
                    clock_in=cin,
                    clock_out=cout,
                    break_start=bstart,
                    break_end=bend,
                    total_break_minutes=60,
                    total_work_minutes=490,
                    status="LEFT",
                    is_corrected=False
                ))

            if weekday in [1, 3, 5]:
                # staff02 勤務実績 (5時間実働 = 300分)
                cin = datetime.combine(d, time(9, 25))
                cout = datetime.combine(d, time(15, 30))
                bstart = datetime.combine(d, time(12, 0))
                bend = datetime.combine(d, time(13, 0))
                db.add(models.TimeRecord(
                    user_id=staff2.id,
                    date=d,
                    clock_in=cin,
                    clock_out=cout,
                    break_start=bstart,
                    break_end=bend,
                    total_break_minutes=60,
                    total_work_minutes=305,
                    status="LEFT",
                    is_corrected=False
                ))

        db.commit()

        # 4. 修正申請サンプル (staff02が申請中)
        sample_target_date = today - timedelta(days=2) if today.day > 2 else today
        db.add(models.CorrectionRequest(
            user_id=staff2.id,
            target_date=sample_target_date,
            requested_clock_in=datetime.combine(sample_target_date, time(9, 30)),
            requested_clock_out=datetime.combine(sample_target_date, time(16, 0)),
            requested_break_minutes=60,
            reason="急患対応のため30分延長業務を行いましたが打刻漏れでした。",
            status="PENDING"
        ))
        db.commit()

        # 5. シフト希望サンプル
        # 来月の日付
        next_month = current_month + 1 if current_month < 12 else 1
        next_year = current_year if current_month < 12 else current_year + 1
        db.add_all([
            models.ShiftRequest(
                user_id=staff1.id,
                date=date(next_year, next_month, 10),
                request_type="OFF",
                reason="家族行事のため休み希望",
                status="PENDING"
            ),
            models.ShiftRequest(
                user_id=staff2.id,
                date=date(next_year, next_month, 15),
                request_type="PAID_LEAVE",
                reason="有給休暇の取得希望",
                status="PENDING"
            )
        ])
        db.commit()

        print("初期マスターデータの作成が完了しました！")
        print("管理者: admin / admin123")
        print("スタッフ1: staff01 / staff123 (佐藤 健)")
        print("スタッフ2: staff02 / staff123 (田中 美咲)")

    except Exception as e:
        db.rollback()
        print(f"マスターデータ作成エラー: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
