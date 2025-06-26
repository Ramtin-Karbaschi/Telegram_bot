"""
Constants for the Daraei Academy Telegram bot
"""

# Welcome message for new users
WELCOME_MESSAGE = """
🌟 به ربات آکادمی دارایی خوش آمدید! 🌟

این ربات به شما امکان عضویت، مدیریت اشتراک و ارتباط با پشتیبانی را می‌دهد.

برای شروع، لطفاً از منوی زیر گزینه مورد نظر خود را انتخاب کنید.
"""

# Help message
HELP_MESSAGE = """
🌟 <b>راهنمای جامع ربات آکادمی دارایی</b> 🌟

سلام! برای استفاده بهتر از امکانات ربات، به موارد زیر توجه کنید:

🔹 <b>شروع کار با ربات:</b>
   • اگر کاربر جدید هستید، با انتخاب گزینه «📝 ثبت نام» اطلاعات اولیه خود را وارد کنید.
   • اگر قبلاً ثبت نام کرده‌اید، می‌توانید با گزینه «🎫 خرید محصولات» اشتراک خود را تهیه یا تمدید کنید.

🔹 <b>دسترسی سریع:</b>
   • <b><i>«💡 راهنما»</i></b>: (همین پیام) برای آشنایی با عملکردهای ربات
   • <b><i>«🤝🏻 پشتیبانی»</i></b>: برای ارتباط مستقیم با تیم پشتیبانی
   • <b><i>«📜 قوانین»</i></b>: برای مطالعه قوانین و مقررات استفاده از خدمات آکادمی دارایی

✨ <i>امیدواریم تجربه خوبی با ربات آکادمی دارایی داشته باشید!</i> ✨
"""

# Rules message
RULES_MESSAGE = """
📜 <b>قوانین آکادمی دارایی</b>:

1️⃣ احترام به سایر اعضا و رعایت ادب در گفتگوها الزامی است.

2️⃣ اطلاعات شخصی شما، نزد آکادمی دارایی محفوظ خواهد بود و ذخیره آن صرفاً به منظور خدمت‌رسانی بهتر خواهد بود.

3️⃣ اشتراک گذاری محتوای آموزشی کانال با دیگران ممنوع است.

4️⃣ استفاده از یک اکانت برای چند نفر مجاز نیست و در صورت تشخیص، عضویت لغو خواهد شد.

5️⃣ آکادمی دارایی حق تغییر در محتوا و قیمت‌ها را برای خود محفوظ می‌دارد.

6️⃣ مسئولیت تصمیمات مالی شما بر عهده خودتان است و آموزش‌های ارائه شده صرفاً جنبه آموزشی دارند.

7️⃣ پرداخت حق عضویت به معنی پذیرش این قوانین است.
"""

# Main Menu Button Texts
TEXT_MAIN_MENU_BUY_SUBSCRIPTION = "🎫 خرید محصولات"
TEXT_MAIN_MENU_STATUS = "👤 پروفایل کاربری"
TEXT_BACK_TO_MAIN_MENU = " بازگشت به منوی اصلی"

# Profile Editing specific constants
PROFILE_EDIT_MENU_PROMPT = "کدام بخش از اطلاعات خود را می‌خواهید ویرایش کنید؟"
PROFILE_EDIT_CITY_PROMPT = "📍 لطفاً شهر جدید محل سکونت خود را وارد کنید:"
PROFILE_EDIT_EMAIL_PROMPT = "📧 لطفاً آدرس ایمیل جدید خود را وارد کنید:"

# Registration steps messages
REGISTRATION_WELCOME = """
🔑 به فرآیند عضویت در آکادمی دارایی خوش آمدید!

📱 لطفاً با استفاده از دکمه زیر، شماره تماس خود را به اشتراک بگذارید.
"""

PHONE_REQUEST = """
""" #delete this line

FULLNAME_REQUEST = """
👤 لطفاً نام و نام خانوادگی خود را وارد کنید.
"""

BIRTHYEAR_REQUEST = """
🗓 لطفاً سال تولد شمسی خود را به صورت عدد وارد کنید (مثال: ۱۳۷۰).
"""

EDUCATION_REQUEST = """
🎓 لطفاً میزان تحصیلات خود را از گزینه‌های زیر انتخاب کنید.
"""

OCCUPATION_REQUEST = """
💼 لطفاً حیطه فعالیت خود را از گزینه‌های زیر انتخاب کنید.
"""

EDIT_OCCUPATION = "edit_occupation_state"
EDIT_PHONE = "edit_phone_state"
EDIT_CITY = "edit_city_state"
EDIT_EMAIL = "edit_email_state"

SUBSCRIPTION_PLANS_MESSAGE = """
📋 لطفاً محصول مورد نظر خود را انتخاب کنید:
"""

CITY_REQUEST = """
📍 لطفاً شهر محل سکونت خود را وارد کنید:
"""

CALLBACK_PROFILE_EDIT_CANCEL = 'profile_edit_cancel'
CALLBACK_PROFILE_EDIT_PHONE = "profile_edit_phone"
CALLBACK_PROFILE_EDIT_CITY = "profile_edit_city"
CALLBACK_PROFILE_EDIT_EMAIL = "profile_edit_email"

CALLBACK_BACK_TO_MAIN_MENU = 'back_to_main_menu'
CALLBACK_MAIN_MENU = 'main_menu'

# Constants for payment flow
PAYMENT_METHOD_MESSAGE = """
💳 روش پرداخت برای طرح «{plan_name}»
قیمت ریالی: {plan_price} ریال
قیمت تتر: {plan_tether} USDT

لطفاً روش پرداخت مورد نظر خود را انتخاب کنید:
"""

CRYPTO_PAYMENT_UNIQUE_AMOUNT_MESSAGE = """
💰 <b>پرداخت با تتر (USDT TRC20)</b> 💰

لطفاً مبلغ دقیقاً <code>{usdt_amount}</code> USDT (شبکه TRC20) را به آدرس کیف پول زیر واریز نمایید:

آدرس کیف پول:
<code>{wallet_address}</code>

(با کلیک روی آدرس یا مبلغ، می‌توانید آن را کپی کنید)

⏳ <b>مهم:</b> لطفاً <b>دقیقاً همین مقدار</b> را واریز کنید تا پرداخت شما به درستی شناسایی شود.

⏰ شما <b>{timeout_minutes} دقیقه</b> برای تکمیل این پرداخت فرصت دارید.

پس از واریز، روی دکمه «تراکنش را انجام دادم، بررسی شود» کلیک کنید.
"""

PAYMENT_SUCCESS_MESSAGE = """
✅ پرداخت شما با موفقیت انجام شد!

🔗 لینک ورود به کانال برای شما فعال شده است. این لینک تنها یکبار قابل استفاده است و پس از ورود به کانال غیرفعال می‌شود.
"""

PAYMENT_ERROR_MESSAGE = """
❌ متأسفانه پرداخت شما تأیید نشد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.
"""

# More Specific Zarinpal Payment Messages (used in start_handler deep link flow)

ZARINPAL_PAYMENT_NOT_FOUND_MESSAGE_USER = "اطلاعات پرداخت با این مشخصات یافت نشد. لطفاً با پشتیبانی تماس بگیرید."
ZARINPAL_PAYMENT_ALREADY_VERIFIED_MESSAGE_USER = "این پرداخت قبلاً با موفقیت تأیید شده است و اشتراک شما فعال می‌باشد."
ZARINPAL_PAYMENT_FAILED_MESSAGE_TRY_AGAIN_USER = "پرداخت شما ناموفق بود یا توسط شما لغو شد (وضعیت: {status}). لطفاً دوباره تلاش کنید یا روش پرداخت دیگری را انتخاب نمایید."
ZARINPAL_PAYMENT_VERIFIED_SUCCESS_AND_SUB_ACTIVATED_MESSAGE_USER = "پرداخت شما با موفقیت تأیید شد. اشتراک پلن '{plan_name}' برای شما فعال گردید. \n (کد رهگیری: {ref_id})"
ZARINPAL_PAYMENT_VERIFIED_SUCCESS_SUB_ACTIVATION_FAILED_MESSAGE_USER = "پرداخت شما با موفقیت تأیید شد (کد رهگیری: {ref_id})، اما در فعال‌سازی اشتراک خطایی رخ داد. لطفاً فوراً با پشتیبانی تماس بگیرید."
ZARINPAL_PAYMENT_VERIFIED_SUCCESS_PLAN_NOT_FOUND_MESSAGE_USER = "پرداخت شما با موفقیت تأیید شد (کد رهگیری: {ref_id})، اما اطلاعات پلن یافت نشد. لطفاً با پشتیبانی تماس بگیرید."
ZARINPAL_PAYMENT_VERIFICATION_FAILED_MESSAGE_USER = "تأیید پرداخت با خطا مواجه شد (کد خطا: {error_code}). در صورت کسر وجه، مبلغ طی ۷۲ ساعت به حساب شما باز خواهد گشت. لطفاً با پشتیبانی تماس بگیرید."
ZARINPAL_PAYMENT_CANCELLED_MESSAGE_USER = "پرداخت توسط شما لغو شد."
GENERAL_ERROR_MESSAGE_USER = "متاسفانه خطایی رخ داده است. لطفا دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."

SUBSCRIPTION_STATUS_NONE = """
❌ شما در حال حاضر اشتراک فعالی ندارید.

برای خرید محصولات، لطفاً یکی از گزینه‌های زیر را انتخاب کنید:
"""

SUBSCRIPTION_STATUS_ACTIVE = """
✅ وضعیت اشتراک شما:

📅 نوع اشتراک: {plan_name}
🗓 تاریخ شروع: {start_date}
🗓 تاریخ پایان: {end_date}
⏱ زمان باقی‌مانده: {days_left} روز
💳 روش پرداخت: {payment_method}
💰 مبلغ پرداختی: {payment_amount}

برای تمدید اشتراک، می‌توانید از دکمه زیر استفاده کنید:
"""

SUBSCRIPTION_STATUS_EXPIRED = """
⚠️ اشتراک شما منقضی شده است:

📅 نوع اشتراک: {plan_name}
🗓 تاریخ شروع: {start_date}
🗓 تاریخ پایان: {end_date}
💳 روش پرداخت: {payment_method}
💰 مبلغ پرداختی: {payment_amount}

برای تمدید اشتراک، لطفاً از دکمه زیر استفاده کنید:
"""

# Admin panel callback patterns

# Zarinpal Status Codes (Numerical)
ZARINPAL_REQUEST_SUCCESS_STATUS = 100  # Status code for a successful payment request (used by Zarinpal service)
ZARINPAL_VERIFY_SUCCESS_STATUS = 100   # Status code for a successful payment verification
ZARINPAL_ALREADY_VERIFIED_STATUS = 101 # Status code for an already verified payment

# Payment Callback Patterns
VERIFY_ZARINPAL_PAYMENT_CALLBACK = "payment_verify_zarinpal"

# General Callbacks and Texts
CALLBACK_BACK_TO_MAIN_MENU = "main_menu_back"
TEXT_GENERAL_BACK_TO_MAIN_MENU = "مشاهده اطلاعات کاربری"
TEXT_GENERAL_BACK = "بازگشت"  # General back button text
TEXT_BACK_BUTTON = "مشاهده اطلاعات کاربری"

CALLBACK_VIEW_SUBSCRIPTION_STATUS_FROM_REG = "view_sub_status_reg"

# Support Conversation States
SUPPORT_MENU, NEW_TICKET_SUBJECT, NEW_TICKET_MESSAGE, VIEW_TICKET = range(4) # For support ConversationHandler

# Support ticket messages
NEW_TICKET_SUBJECT_REQUEST = """
📝 برای ثبت تیکت جدید، لطفاً موضوع تیکت خود را وارد کنید:
"""

TICKET_CLOSED_MESSAGE = """
🔴 تیکت بسته شد.

در صورتی که مشکل شما حل نشده است، می‌توانید تیکت را مجدداً باز کنید.
"""

TICKET_REOPENED_MESSAGE = """
🟢 تیکت مجدداً باز شد.

می‌توانید به گفتگو ادامه دهید.
"""

# Manager bot messages
MEMBERSHIP_EXPIRED = """
⚠️ کاربر گرامی،

متأسفانه اشتراک شما در آکادمی دارایی به پایان رسیده است و دسترسی شما به کانال غیرفعال شده است.

برای تمدید اشتراک، لطفاً به ربات @Daraei_Academy_bot مراجعه کنید و از گزینه "وضعیت اشتراک من" استفاده نمایید.
"""

# Admin panel callback patterns

# Zarinpal Status Codes (Numerical)
ZARINPAL_REQUEST_SUCCESS_STATUS = 100  # Status code for a successful payment request (used by Zarinpal service)
ZARINPAL_VERIFY_SUCCESS_STATUS = 100   # Status code for a successful payment verification
ZARINPAL_ALREADY_VERIFIED_STATUS = 101 # Status code for an already verified payment

# Payment Callback Patterns
VERIFY_ZARINPAL_PAYMENT_CALLBACK = "payment_verify_zarinpal"

# General Callbacks and Texts
CALLBACK_BACK_TO_MAIN_MENU = "main_menu_back"
TEXT_GENERAL_BACK_TO_MAIN_MENU = "مشاهده اطلاعات کاربری"
TEXT_GENERAL_BACK = "بازگشت"  # General back button text

CALLBACK_VIEW_SUBSCRIPTION_STATUS_FROM_REG = "view_sub_status_reg"

# Support Conversation States
SUPPORT_MENU, NEW_TICKET_SUBJECT, NEW_TICKET_MESSAGE, VIEW_TICKET = range(4) # For support ConversationHandler

# Support ticket messages
NEW_TICKET_SUBJECT_REQUEST = """
📝 برای ثبت تیکت جدید، لطفاً موضوع تیکت خود را وارد کنید:
"""

TICKET_CLOSED_MESSAGE = """
🔴 تیکت بسته شد.

در صورتی که مشکل شما حل نشده است، می‌توانید تیکت را مجدداً باز کنید.
"""

TICKET_REOPENED_MESSAGE = """
🟢 تیکت مجدداً باز شد.

می‌توانید به گفتگو ادامه دهید.
"""

# Manager bot messages
MEMBERSHIP_EXPIRED = """
⚠️ کاربر گرامی،

متأسفانه اشتراک شما در آکادمی دارایی به پایان رسیده است و دسترسی شما به کانال غیرفعال شده است.

برای تمدید اشتراک، لطفاً به ربات @Daraei_Academy_bot مراجعه کنید و از گزینه "وضعیت اشتراک من" استفاده نمایید.
"""