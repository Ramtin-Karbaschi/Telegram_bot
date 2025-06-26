"""
اسکریپت تست برای بررسی عملکرد پایگاه داده
"""

from database.queries import DatabaseQueries as Database
from database.models import Database as DBConnection
import config

def test_database_operations():
    """تست عملیات اصلی پایگاه داده"""
    print("شروع تست پایگاه داده...")
    
    # بررسی مسیر پایگاه داده
    print(f"مسیر پایگاه داده: {config.DATABASE_NAME}")
    
    # تست اتصال مستقیم به پایگاه داده
    db = DBConnection()
    if db.connect():
        print("✅ اتصال موفق به پایگاه داده")
        db.close()
    else:
        print("❌ خطا در اتصال به پایگاه داده")
        return
    
    # تست افزودن کاربر
    test_user_id = 12345678
    username = "test_user_persian"
    
    # حذف کاربر در صورت وجود
    db = DBConnection()
    if db.connect():
        db.execute("DELETE FROM users WHERE user_id = ?", (test_user_id,))
        db.commit()
        db.close()
        print(f"🧹 کاربر تست موجود {test_user_id} حذف شد")
    
    # بررسی عدم وجود کاربر در پایگاه داده
    if Database.user_exists(test_user_id):
        print(f"❌ خطا: کاربر {test_user_id} هنوز وجود دارد")
        return
    else:
        print(f"✅ تأیید شد که کاربر {test_user_id} وجود ندارد")
    
    # افزودن کاربر
    if Database.add_user(test_user_id, username=username):
        print(f"✅ کاربر {test_user_id} با موفقیت اضافه شد")
    else:
        print(f"❌ خطا در افزودن کاربر {test_user_id}")
        return
    
    # بررسی وجود کاربر
    if Database.user_exists(test_user_id):
        print(f"✅ تأیید شد که کاربر {test_user_id} وجود دارد")
    else:
        print(f"❌ خطا: کاربر {test_user_id} پس از افزودن یافت نشد")
        return
    
    # به‌روزرسانی پروفایل کاربر
    full_name = "کاربر تست فارسی"
    phone = "+989123456789"
    birth_year = 1370
    age = 34 # This will be recalculated based on current Shamsi year if logic is in place
    education = "کارشناسی"
    occupation = "ارز، طلا، سکه"
    
    if Database.update_user_profile(
        test_user_id,
        full_name=full_name,
        phone=phone,
        age=age, # Note: age might be overwritten if calculated from birth_year
        birth_year=birth_year,
        education=education,
        occupation=occupation
    ):
        print(f"✅ پروفایل کاربر {test_user_id} با موفقیت به‌روزرسانی شد")
    else:
        print(f"❌ خطا در به‌روزرسانی پروفایل کاربر {test_user_id}")
        return
    
    # دریافت اطلاعات کاربر
    user_details = Database.get_user_details(test_user_id)
    if user_details:
        print(f"✅ اطلاعات کاربر {test_user_id} با موفقیت دریافت شد:")
        print(f"  - شناسه: {user_details['user_id']}")
        print(f"  - نام کاربری: {user_details['username']}")
        print(f"  - نام کامل: {user_details['full_name']}")
        print(f"  - تلفن: {user_details['phone']}")
        print(f"  - سال تولد: {user_details['birth_year']}")
        print(f"  - سن: {user_details['age']}")
        print(f"  - تحصیلات: {user_details['education']}")
        print(f"  - حیطه فعالیت: {user_details['occupation']}")
        print(f"  - تاریخ ثبت‌نام: {user_details['registration_date']}")
    else:
        print(f"❌ خطا در دریافت اطلاعات کاربر {test_user_id}")
        return
    
    # بررسی وضعیت ثبت‌نام کاربر
    if Database.is_registered(test_user_id):
        print(f"✅ کاربر {test_user_id} به درستی به عنوان ثبت‌نام شده علامت‌گذاری شده است")
    else:
        print(f"❌ خطا: کاربر {test_user_id} به عنوان ثبت‌نام شده علامت‌گذاری نشده است")
    
    print("\nتست پایگاه داده با موفقیت به پایان رسید!")

if __name__ == "__main__":
    test_database_operations()
