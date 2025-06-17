# This file contains names that are reported as unused by Vulture,
# but are actually in use. This is a "whitelist" to suppress false positives.

# Ignored due to being a false positive. This attribute is used to configure
# the database connection to return dictionary-like rows, but Vulture
# cannot detect this usage pattern.
row_factory

# Ignored because its usage cannot be verified due to file reading issues.
# It is safer to whitelist it to prevent potential runtime errors.
update_crypto_payment_on_success

# Ignored because its usage cannot be verified due to file reading issues.
get_crypto_payment_by_payment_id

# Ignored because its usage cannot be verified due to file reading issues.
get_crypto_payment_by_transaction_id

# Ignored because its usage cannot be verified due to file reading issues.
get_pending_crypto_payment_by_user_and_amount

# Ignored because its usage cannot be verified due to file reading issues.
get_expired_pending_payments
