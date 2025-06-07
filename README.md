# Daraei Academy Telegram Bot

ربات تلگرامی آکادمی دارایی برای مدیریت کاربران، اشتراک‌ها و ارائه خدمات به اعضا.

## ویژگی‌ها

*   ثبت‌نام کاربران و جمع‌آوری اطلاعات پروفایل.
*   ویرایش پروفایل توسط کاربران.
*   سیستم اشتراک با سطوح مختلف (ماهانه، سه‌ماهه، شش‌ماهه، سالیانه).
*   پرداخت از طریق درگاه ریالی و تتر (USDT).
*   مدیریت وضعیت اشتراک کاربران.
*   ارسال یادآوری برای تمدید اشتراک.
*   سیستم تیکتینگ برای پشتیبانی.
*   منوی اصلی با دسترسی آسان به قابلیت‌ها.

## پیش‌نیازها

*   Python 3.8 یا بالاتر
*   Pip (مدیریت پکیج پایتون)

## نصب و راه‌اندازی

1.  **کلون کردن ریپازیتوری (در صورت وجود):**
    ```bash
    git clone <repository_url>
    cd telegram_bot
    ```

2.  **ایجاد و فعال‌سازی محیط مجازی (توصیه می‌شود):**
    ```bash
    python -m venv venv
    # On Windows
    venv\\Scripts\\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **نصب وابستگی‌ها:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **تنظیم متغیرهای محیطی:**
    یک فایل با نام `.env` در ریشه پروژه (کنار [config.py](cci:7://file:///e:/Learning/AI/Daraie%20Academy/telegram_bot/config.py:0:0-0:0)) ایجاد کنید و متغیرهای زیر را با مقادیر مناسب پر کنید:

    ```env
    MAIN_BOT_TOKEN="YOUR_MAIN_TELEGRAM_BOT_TOKEN"
    MANAGER_BOT_TOKEN="YOUR_MANAGER_TELEGRAM_BOT_TOKEN"

    # اطلاعات کانال تلگرام (جایگزین کنید)
    TELEGRAM_CHANNEL_ID="@your_channel_username_or_id" # مثال: -1001234567890 یا @daraei_academy_channel
    TELEGRAM_CHANNEL_TITLE="نام کانال شما"
    TELEGRAM_CHANNEL_LINK="https://t.me/your_channel_link"

    # اطلاعات درگاه پرداخت (جایگزین کنید)
    PAYMENT_GATEWAY_URL="YOUR_PAYMENT_GATEWAY_API_URL"
    PAYMENT_CALLBACK_URL="YOUR_PAYMENT_GATEWAY_CALLBACK_URL"
    PAYMENT_API_KEY="YOUR_PAYMENT_GATEWAY_API_KEY"

    # آدرس کیف پول تتر (جایگزین کنید)
    TETHER_WALLET_ADDRESS="YOUR_TETHER_TRC20_WALLET_ADDRESS"
    ```
    **توجه:** مقادیر مربوط به توکن‌ها، کانال، درگاه پرداخت و کیف پول تتر باید با اطلاعات واقعی شما جایگزین شوند.

5.  **راه‌اندازی اولیه دیتابیس:**
    فایل [initialize_db.py](cci:7://file:///e:/Learning/AI/Daraie%20Academy/telegram_bot/initialize_db.py:0:0-0:0) (یا هر اسکریپتی که برای این منظور در نظر گرفته شده) را برای ایجاد جداول اولیه دیتابیس اجرا کنید:
    ```bash
    python initialize_db.py
    ```
    (اگر نام فایل متفاوت است، لطفاً آن را جایگزین کنید. ممکن است این مرحله به عنوان بخشی از اجرای اصلی ربات نیز انجام شود.)

6.  **اجرای ربات اصلی:**
    ```bash
    python bots/main_bot.py
    ```

## ساختار پروژه (نمای کلی)

```text
telegram_bot/
├── bots/                     # کدهای مربوط به ربات اصلی و ربات مدیریت
│   ├── main_bot.py
│   └── manager_bot.py
├── config.py                 # تنظیمات اصلی و کلیدهای API (از متغیرهای محیطی خوانده می‌شود)
├── database/                 # ماژول‌های مربوط به دیتابیس
│   ├── data/                 # پوشه فایل دیتابیس SQLite
│   │   └── daraei_academy.db # (ایجاد شده پس از اولین اجرا یا توسط initialize_db.py)
│   ├── models.py             # کلاس اصلی مدیریت اتصال به دیتابیس (Database)
│   ├── queries.py            # کلاس شامل کوئری‌های دیتابیس (DatabaseQueries)
│   └── schema.py             # اسکریپت تعریف و ایجاد جداول اولیه دیتابیس
├── handlers/                 # کنترل‌کننده‌های ربات برای مدیریت دستورات و پیام‌ها
│   ├── core/                 #   زیرپوشه: کنترل‌کننده‌های اصلی (start, menu, help)
│   ├── payment/              #   زیرپوشه: کنترل‌کننده‌های مربوط به پرداخت
│   ├── registration/         #   زیرپوشه: کنترل‌کننده‌های مربوط به ثبت‌نام
│   ├── subscription/         #   زیرپوشه: کنترل‌کننده‌های مربوط به اشتراک
│   ├── support/              #   زیرپوشه: کنترل‌کننده‌های مربوط به پشتیبانی
│   └── profile_handlers.py   #   فایل: کنترل‌کننده‌های مربوط به ویرایش پروفایل کاربر
├── services/                 # سرویس‌های خارجی (مانند سرویس پرداخت)
│   └── payment_service.py    # (مثال، در صورت وجود)
├── utils/                    # ابزارها و توابع کمکی
│   ├── constants/            #   زیرپوشه: ثابت‌های متنی و مقادیر ثابت
│   ├── keyboards/            #   زیرپوشه: توابع ایجاد کیبوردهای تلگرام
│   └── validators.py         #   فایل: توابع اعتبارسنجی ورودی‌ها
├── .env.example              # نمونه فایل برای متغیرهای محیطی (توصیه می‌شود ایجاد کنید)
├── initialize_db.py          # اسکریپت برای راه‌اندازی و ایجاد جداول اولیه دیتابیس
├── requirements.txt          # لیست پکیج‌های مورد نیاز پایتون
├── README.md                 # همین فایل راهنما
└── run.py                    # اسکریپت اصلی برای اجرای ربات (ها) (در صورت وجود)


## مشارکت

در صورت تمایل به مشارکت، لطفاً یک Issue باز کنید یا یک Pull Request ارسال نمایید.