"""
Constants for the Daraei Academy Telegram bot
"""

from .all_constants import *

# Main Menu Button Text for users not yet fully registered

# Welcome message for new users
WELCOME_MESSAGE = """
🌟 به ربات آکادمی دارایی خوش آمدید! 🌟

این ربات به شما امکان دسترسی به تحلیل‌های بازارهای مالی، آموزش‌ها و مدیریت پورتفو را می‌دهد. برای شروع، می‌توانید از طریق گزینه «📝 ثبت نام» اطلاعات خود را وارد کرده و سپس با انتخاب «🎫 خرید محصولات» اشتراک مورد نظر خود را تهیه نمایید.

از منوی اصلی می‌توانید به بخش‌های مختلف از جمله پروفایل، وضعیت اشتراک، پشتیبانی و قوانین دسترسی داشته باشید. برای آشنایی بیشتر با امکانات ربات، گزینه «💡 راهنما» را انتخاب کنید.
"""

# Help message
HELP_MESSAGE = """
🔍 راهنمای ربات آکادمی دارایی:

• برای ثبت‌نام اولیه و دسترسی به امکانات ربات، گزینه «📝 ثبت نام» را انتخاب کنید. در این مرحله تنها شماره تماس و نام شما دریافت می‌شود.
• برای مشاهده وضعیت اشتراک خود و همچنین تکمیل یا اصلاح سایر اطلاعات پروفایل (مانند سال تولد، تحصیلات و...)، گزینه «👤 وضعیت اشتراک من» را انتخاب نمایید.
• برای ارتباط با پشتیبانی، گزینه «🤝🏻 پشتیبانی» را انتخاب کنید.
• برای مشاهده قوانین و مقررات استفاده از ربات و خدمات، گزینه «⚠ قوانین» را انتخاب کنید.

پس از تکمیل ثبت نام اولیه، می‌توانید در هر زمان از طریق منوی «👤 وضعیت اشتراک من» و سپس گزینه «اصلاح و تکمیل اطلاعات»، پروفایل خود را کامل کنید.

در صورت نیاز به راهنمایی بیشتر یا بروز هرگونه مشکل، با تیم پشتیبانی ما در ارتباط باشید.
"""

# Rules message
RULES_MESSAGE = """
<b>📜 قوانین آکادمی دارایی:</b>
<code>❌توجه داشته باشید، ❌ قوانین و تفاهم نامه را با دقت مطالعه کنید.</code>

1️⃣ در این کانال، داده‌های فاندامنتال (بنیادی) و تحلیل‌های کوتاه‌مدت و میان‌مدت بازارهای بورس و کریپتو منتشر می‌شود. با عضویت در کانال به تحلیل‌های گذشته نیز دسترسی خواهید داشت؛ بنابراین اشتراک صرفاً محدود به داده‌های بعد از تاریخ عضویت نیست. توجه داشته باشید مبلغ پرداختی اشتراک قابل بازگشت نیست.

2️⃣ محتوای کانال شامل تحلیل، مدیریت پورتفو و آموزش جهت ارتقای سطح معامله‌گری شماست.

3️⃣ می‌توانید از پشتیبانی کانال سؤال بپرسید؛ پرسش‌های شما به‌صورت روزانه پاسخ داده می‌شود.

4️⃣ مشترکین آکادمی دارایی کد تخفیف اختصاصی برای محصولات آینده دریافت خواهند کرد.

5️⃣ 🛑 فقط حساب تلگرامی که اشتراک خریده می‌تواند در کانال عضو باشد. در صورت به‌اشتراک‌گذاری لینک با دیگران، حساب دوم به‌صورت خودکار حذف خواهد شد.

6️⃣ مسئولیت استفاده صحیح از محتوای کانال بر عهده شماست. آکادمی دارایی تمام تلاش خود را برای بهبود وضعیت معاملاتی و افزایش دارایی شما می‌کند اما نحوه استفاده از داده‌ها به عهده خود شماست.

7️⃣ آکادمی دارایی توصیه‌ای به معاملات فیوچرز یا معاملات با ریسک بسیار بالا که ممکن است منجر به از دست رفتن سرمایه شود ندارد؛ نگهبان سرمایه خود باشید.
"""

# Registration steps messages
REGISTRATION_WELCOME = """
🔑 به فرآیند عضویت در آکادمی دارایی خوش آمدید!

برای ادامه، لطفاً اطلاعات خود را به ترتیب وارد کنید.
"""

PHONE_REQUEST = """
📱 لطفاً با استفاده از دکمه زیر، شماره تماس خود را به اشتراک بگذارید.
"""

FULLNAME_REQUEST = """
👤 لطفاً نام و نام خانوادگی خود را وارد کنید.
"""

BIRTHYEAR_REQUEST = """
🗓 لطفاً سال تولد خود را به صورت عدد وارد کنید (مثال: 1370).
"""

EDUCATION_REQUEST = """
🎓 لطفاً میزان تحصیلات خود را از گزینه‌های زیر انتخاب کنید.
"""

OCCUPATION_REQUEST = """
💼 لطفاً حیطه فعالیت خود را از گزینه‌های زیر انتخاب کنید.
"""

# Subscription status constants
SUBSCRIPTION_STATUS_NONE = "شما در حال حاضر اشتراک فعالی ندارید."
SUBSCRIPTION_STATUS_ACTIVE = """
اشتراک شما فعال است.
نام طرح: {plan_name}
روزهای باقیمانده: {days_left}
تاریخ شروع: {start_date}
تاریخ انقضا: {end_date}
"""
SUBSCRIPTION_STATUS_EXPIRED = """
اشتراک شما منقضی شده است.
نام طرح: {plan_name}
تاریخ شروع: {start_date}
تاریخ انقضا: {end_date}
"""

# Subscription messages
SUBSCRIPTION_PLANS_MESSAGE = """
📋 لطفاً محصول مورد نظر خود را انتخاب کنید:
"""

PAYMENT_SUCCESS_MESSAGE = """
✅ پرداخت شما با موفقیت انجام شد!

اطلاعات اشتراک:
طرح: {plan_name}
مدت اعتبار باقیمانده: {days_left} روز

اکنون می‌توانید به کانال آکادمی دارایی دسترسی داشته باشید.
"""

PAYMENT_FAILED_MESSAGE = """
❌ متأسفانه پرداخت شما تأیید نشد.

لطفاً مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید.
"""

# Alias for backward compatibility (old name used in some handlers)
PAYMENT_ERROR_MESSAGE = PAYMENT_FAILED_MESSAGE

# Profile Editing States for ConversationHandler
SELECT_FIELD_TO_EDIT = "SELECT_FIELD_TO_EDIT"
EDIT_FULL_NAME = "EDIT_FULL_NAME"
EDIT_BIRTH_YEAR = "EDIT_BIRTH_YEAR"  # now represents full birth date
EDIT_EDUCATION = "EDIT_EDUCATION"
EDIT_OCCUPATION = "EDIT_OCCUPATION"
SELECT_OCCUPATION = "SELECT_OCCUPATION"
EDIT_PHONE = "EDIT_PHONE"

# Callback data to directly start profile editing (e.g., from another menu)
CALLBACK_START_PROFILE_EDIT = "start_profile_edit_conversation"

# Main Menu Texts
TEXT_MAIN_MENU_HELP = "💡 راهنما"

TEXT_MAIN_MENU_REGISTRATION = "📝 ثبت نام"
TEXT_MAIN_MENU_EDIT_PROFILE = "👤 ویرایش پروفایل"
TEXT_MAIN_MENU_SUPPORT = "🤝🏻 پشتیبانی"
TEXT_MAIN_MENU_RULES = "⚠ قوانین"
TEXT_MAIN_MENU_BUY_SUBSCRIPTION = "🛒 محصولات"
TEXT_MAIN_MENU_FREE_PACKAGE = "🎁 رایگان"

# Profile Editing Callback Data
CALLBACK_PROFILE_EDIT_FULLNAME = "edit_profile_fullname"
CALLBACK_PROFILE_EDIT_BIRTHYEAR = "edit_profile_birthyear"
CALLBACK_PROFILE_EDIT_EDUCATION = "edit_profile_education"
CALLBACK_PROFILE_EDIT_OCCUPATION = "edit_profile_occupation"
CALLBACK_PROFILE_EDIT_OCCUPATION_CONFIRM = "edit_profile_occupation_confirm"
CALLBACK_PROFILE_EDIT_PHONE = "edit_profile_phone"
CALLBACK_PROFILE_EDIT_BACK_TO_MENU = "edit_profile_back_to_menu"
CALLBACK_PROFILE_EDIT_CANCEL = "edit_profile_cancel"
CALLBACK_BACK_TO_MAIN_MENU_FROM_EDIT = "back_to_main_menu_from_edit"

# General UI Texts

# Callback Data for custom flows

# Profile Editing Messages
PROFILE_EDIT_MENU_PROMPT = "کدام بخش از اطلاعات خود را می‌خواهید ویرایش کنید؟"
PROFILE_EDIT_FULL_NAME = "لطفاً نام و نام خانوادگی جدید خود را وارد کنید:"
PROFILE_EDIT_BIRTH_YEAR = "🗓 تاریخ تولد (روز/ماه/سال شمسی) — مثال: ۱۳۷۰/۱/۱۵"
PROFILE_EDIT_EDUCATION = "لطفاً میزان تحصیلات جدید خود را از گزینه‌های زیر انتخاب کنید:"
PROFILE_EDIT_OCCUPATION = "لطفاً حیطه فعالیت خود را از گزینه‌های زیر انتخاب کنید:"
PROFILE_EDIT_FIELD_SUCCESS = "✅ {field_name} شما با موفقیت به‌روزرسانی شد."
PROFILE_EDIT_CANCELLED = "عملیات ویرایش اطلاعات لغو شد."
PROFILE_EDIT_FIELD_CANCELLED = "ویرایش {field_name} لغو شد."
PROFILE_INVALID_BIRTHYEAR = "تاریخ تولد نامعتبر است. قالب درست: ۱۳۷۰/۱/۱۵ — سال بین ۱۳۲۰ تا ۱۳۸۶."
PROFILE_ASK_PHONE_EDIT_WITH_CONTACT = "لطفاً شماره تلفن جدید خود را وارد کنید یا با دکمه زیر به اشتراک بگذارید:"
REPLY_KEYBOARD_BACK_TO_EDIT_MENU_TEXT = "بازگشت به منوی ویرایش"

# Support ticket messages
SUPPORT_WELCOME_MESSAGE = """
👨‍💻 به بخش پشتیبانی خوش آمدید!

سوال دارید؟
از پشتیبانی ما بپرسید

@daraeiposhtibani ✅

⚠️ دوستان ما یک اکانت پشتیبانی بیشتر نداریم. 
فریب اکانت های مشابه را نخورید.

همچنین از اینجا می‌توانید تیکت جدید ایجاد کنید یا تیکت‌های قبلی خود را به همراه پاسخ آنها مشاهده کنید.
"""

NEW_TICKET_SUBJECT_REQUEST = """
📝 لطفاً موضوع تیکت خود را وارد کنید:
"""

TICKET_CLOSED_MESSAGE = """
🔴 تیکت #{ticket_id} بسته شد.
"""

TICKET_REOPENED_MESSAGE = """
🟢 تیکت #{ticket_id} مجدداً باز شد.
"""
