import json
import calendar
from datetime import datetime, date, time, timedelta
from database import SessionLocal, engine, Base
from auth import hash_password
import models

def seed_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 既存管理者データの確認
        existing_admin = db.query(models.User).filter(models.User.username == "admin").first()
        if existing_admin:
            # 確定仕様に合わせて管理者氏名を同期
            existing_admin.full_name = "三宅 智之（管理薬剤師）"
            db.commit()
            print("管理者アカウント（三宅 智之 様）が存在します。")
            return

        # 既存ユーザーが1人でも存在する場合は初期シードを実行しない（削除されたスタッフを復活させない）
        if db.query(models.User).count() > 0:
            print("ユーザーデータが存在するため、初期シードをスキップします。")
            return

        print("初期マスターデータ（初回起動時のみ）を作成中...")

        # 1. ユーザー作成（三宅様、小林彩乃様、寺内様の3名体制）
        # 三宅 智之（管理薬剤師）: 月火水金 09:00〜19:00, 木土 09:00〜13:00(半日)
        miyake_schedule = json.dumps({
            "0": {"work": True, "start": "09:00", "end": "19:00", "break": 60},
            "1": {"work": True, "start": "09:00", "end": "19:00", "break": 60},
            "2": {"work": True, "start": "09:00", "end": "19:00", "break": 60},
            "3": {"work": True, "start": "09:00", "end": "13:00", "break": 0},
            "4": {"work": True, "start": "09:00", "end": "19:00", "break": 60},
            "5": {"work": True, "start": "09:00", "end": "13:00", "break": 0},
            "6": {"work": False, "start": "09:00", "end": "18:00", "break": 0}
        })
        admin_user = models.User(
            username="admin",
            password_hash=hash_password("admin123"),
            full_name="三宅 智之（管理薬剤師）",
            role="admin",
            wage_type="MONTHLY",
            monthly_salary=450000,
            hourly_wage=2800,
            paid_leave_granted=15.0,
            paid_leave_carried=5.0,
            paid_leave_base_date=date(2026, 4, 1),
            work_days="0,1,2,3,4,5",
            weekly_schedule=miyake_schedule,
            default_start_time=time(9, 0),
            default_end_time=time(19, 0),
            default_break_minutes=60,
            color="#7c3aed",
            is_active=True
        )

        # 小林 彩乃（薬剤師）: 月火水金 09:00〜18:00, 土 09:00〜13:00 (時給1,500円)
        kobayashi_schedule = json.dumps({
            "0": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "1": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "2": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "3": {"work": False, "start": "09:00", "end": "18:00", "break": 0},
            "4": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "5": {"work": True, "start": "09:00", "end": "13:00", "break": 0},
            "6": {"work": False, "start": "09:00", "end": "18:00", "break": 0}
        })
        staff1 = models.User(
            username="staff01",
            password_hash=hash_password("staff123"),
            full_name="小林 彩乃（薬剤師）",
            role="staff",
            wage_type="HOURLY",
            hourly_wage=1500,
            monthly_salary=0,
            paid_leave_granted=10.0,
            paid_leave_carried=2.0,
            paid_leave_base_date=date(2026, 4, 1),
            work_days="0,1,2,4,5",
            weekly_schedule=kobayashi_schedule,
            default_start_time=time(9, 0),
            default_end_time=time(18, 0),
            default_break_minutes=60,
            color="#059669",
            is_active=True
        )

        # 寺内（調剤事務）: 月火木金 09:00〜18:00, 土 09:00〜13:00 (時給1,200円)
        terauchi_schedule = json.dumps({
            "0": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "1": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "2": {"work": False, "start": "09:00", "end": "18:00", "break": 0},
            "3": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "4": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
            "5": {"work": True, "start": "09:00", "end": "13:00", "break": 0},
            "6": {"work": False, "start": "09:00", "end": "18:00", "break": 0}
        })
        staff2 = models.User(
            username="staff02",
            password_hash=hash_password("staff123"),
            full_name="寺内（調剤事務）",
            role="staff",
            wage_type="HOURLY",
            hourly_wage=1200,
            monthly_salary=0,
            paid_leave_granted=7.0,
            paid_leave_carried=1.0,
            paid_leave_base_date=date(2026, 4, 1),
            work_days="0,1,3,4,5",
            weekly_schedule=terauchi_schedule,
            default_start_time=time(9, 0),
            default_end_time=time(18, 0),
            default_break_minutes=60,
            color="#0284c7",
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

            # 日曜は全館休局
            if weekday == 6:
                continue

            # 1. 三宅様（管理薬剤師）: 月火水金 9:00〜19:00, 木土 9:00〜13:00
            m_start = time(9, 0)
            m_end = time(13, 0) if weekday in [3, 5] else time(19, 0)
            m_break = 0 if weekday in [3, 5] else 60
            db.add(models.Shift(
                user_id=admin_user.id,
                date=d,
                start_time=m_start,
                end_time=m_end,
                break_minutes=m_break,
                shift_type="NORMAL",
                note="管理薬剤師シフト"
            ))

            # 2. 小林 彩乃（薬剤師）: 月火水金 9:00〜18:00, 土 9:00〜13:00, 木曜休み
            if weekday in [0, 1, 2, 4, 5]:
                k_start = time(9, 0)
                k_end = time(13, 0) if weekday == 5 else time(18, 0)
                k_break = 0 if weekday == 5 else 60
                shift_type = "PAID_LEAVE" if d_num == 15 else "NORMAL"
                db.add(models.Shift(
                    user_id=staff1.id,
                    date=d,
                    start_time=k_start if shift_type == "NORMAL" else None,
                    end_time=k_end if shift_type == "NORMAL" else None,
                    break_minutes=k_break if shift_type == "NORMAL" else 0,
                    shift_type=shift_type,
                    note="薬剤師シフト" if shift_type == "NORMAL" else "計画有休"
                ))

            # 3. 寺内（調剤事務）: 月火木金 9:00〜18:00, 土 9:00〜13:00, 水曜休み
            if weekday in [0, 1, 3, 4, 5]:
                t_start = time(9, 0)
                t_end = time(13, 0) if weekday == 5 else time(18, 0)
                t_break = 0 if weekday == 5 else 60
                db.add(models.Shift(
                    user_id=staff2.id,
                    date=d,
                    start_time=t_start,
                    end_time=t_end,
                    break_minutes=t_break,
                    shift_type="NORMAL",
                    note="調剤事務シフト"
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
        print("管理者: admin / admin123 (三宅 智之)")
        print("スタッフ1: staff01 / staff123 (小林 彩乃)")
        print("スタッフ2: staff02 / staff123 (寺内)")

    except Exception as e:
        db.rollback()
        print(f"マスターデータ作成エラー: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
