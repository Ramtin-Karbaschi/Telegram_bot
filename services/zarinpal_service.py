import logging
from zarinpal.client import ZarinpalClient 
import logging
from config import ZARINPAL_MERCHANT_ID, ZARINPAL_CALLBACK_URL
from utils.constants.all_constants import ZARINPAL_REQUEST_SUCCESS_STATUS, ZARINPAL_VERIFY_SUCCESS_STATUS


logger = logging.getLogger(__name__)


class ZarinpalPaymentService:
    """Service class to interact with Zarinpal payment gateway using zarinpal-python-sdk."""

    _client = None

    @staticmethod
    def _get_client() -> ZarinpalClient:
        """Initializes and returns the ZarinpalClient instance."""
        if ZarinpalPaymentService._client is None:
            if not ZARINPAL_MERCHANT_ID:
                logger.error("Zarinpal merchant ID is not configured.")
                raise ValueError("Zarinpal merchant ID not configured.")
            # For production, sandbox should be False. Assuming it's handled by env or default.
            # The zarinpal-python-sdk defaults to sandbox=False if not specified.
            ZarinpalPaymentService._client = ZarinpalClient(merchant_id=ZARINPAL_MERCHANT_ID, sandbox=False)
            logger.info(f"ZarinpalClient initialized with Merchant ID: {ZARINPAL_MERCHANT_ID[:5]}... and sandbox=False")
        return ZarinpalPaymentService._client

    @staticmethod
    def create_payment_request(amount: int, description: str, user_email: str = None, user_mobile: str = None) -> dict:
        """
        Creates a payment request with Zarinpal using zarinpal-python-sdk.

        Args:
            amount (int): The amount to be paid (in Rials).
            description (str): Description of the transaction.
            user_email (str, optional): User's email. Defaults to None.
            user_mobile (str, optional): User's mobile number. Defaults to None.

        Returns:
            dict: A dictionary containing the status, authority, and payment URL if successful,
                  otherwise status and error message.
        """
        try:
            client = ZarinpalPaymentService._get_client()
            
            if not ZARINPAL_CALLBACK_URL or ZARINPAL_CALLBACK_URL == "https://t.me/YOUR_BOT_USERNAME/payment_callback":
                logger.error("Zarinpal callback URL is not properly configured. Please set it in .env")
                return {'status': -98, 'error_message': 'Zarinpal callback URL not configured.'}

            logger.info(f"Creating Zarinpal payment request. Amount: {amount}, Description: {description}, Callback: {ZARINPAL_CALLBACK_URL}")
            
            response = client.request_payment(
                amount=amount,
                description=description,
                callback_url=ZARINPAL_CALLBACK_URL,
                mobile=user_mobile if user_mobile else None, # Ensure None if empty string
                email=user_email if user_email else None    # Ensure None if empty string
            )
            
            # zarinpal-python-sdk response structure:
            # Success: {'Status': 100, 'Authority': 'A000...', 'PaymentURL': 'https://sandbox.zarinpal.com/pg/StartPay/A000...'}
            # Failure: {'Status': error_code, 'Message': 'Error description'}
            
            status = response.get('Status')
            authority = response.get('Authority')
            
            if status == ZARINPAL_REQUEST_SUCCESS_STATUS and authority:
                # The SDK might provide PaymentURL directly, or we construct it.
                # The SDK's example shows constructing it for sandbox. For production, it's www.zarinpal.com
                # payment_url = response.get('PaymentURL') # Not directly provided by this SDK's request_payment
                payment_url = f"https://www.zarinpal.com/pg/StartPay/{authority}"
                logger.info(f"Zarinpal payment request successful. Authority: {authority}, Payment URL: {payment_url}")
                return {'status': status, 'authority': authority, 'payment_url': payment_url}
            else:
                error_message = response.get('Message', f"Zarinpal request failed with status {status}")
                logger.error(f"Zarinpal payment request failed. Status: {status}, Message: {error_message}")
                return {'status': status, 'error_message': error_message, 'authority': authority}

        except ValueError as ve:
            logger.error(f"ValueError during Zarinpal payment request: {ve}")
            return {'status': -101, 'error_message': str(ve)} 
        except Exception as e:
            logger.exception(f"Exception during Zarinpal payment request: {e}")
            return {'status': -100, 'error_message': str(e)}

    @staticmethod
    def verify_payment(amount: int, authority: str) -> dict:
        """
        Verifies a payment with Zarinpal using zarinpal-python-sdk.

        Args:
            amount (int): The amount that was paid (in Rials).
            authority (str): The authority code received from Zarinpal after payment request.

        Returns:
            dict: A dictionary containing the status and ref_id if successful,
                  otherwise status and error message.
        """
        try:
            client = ZarinpalPaymentService._get_client()
            logger.info(f"Verifying Zarinpal payment. Amount: {amount}, Authority: {authority}")
            
            response = client.verify_payment(authority=authority, amount=amount)
            
            # zarinpal-python-sdk response structure:
            # Success: {'Status': 100, 'RefID': 12345, ...}
            # Already Verified: {'Status': 101, 'RefID': 12345, ...}
            # Failure: {'Status': error_code, 'Message': 'Error description'}
            
            status = response.get('Status')
            ref_id = response.get('RefID')

            if status == ZARINPAL_VERIFY_SUCCESS_STATUS or status == 101: # 101: Already verified
                logger.info(f"Zarinpal payment verification successful. Status: {status}, RefID: {ref_id}")
                return {'status': status, 'ref_id': ref_id}
            else:
                error_message = response.get('Message', f"Zarinpal verification failed with status {status}")
                logger.error(f"Zarinpal payment verification failed. Status: {status}, Message: {error_message}")
                return {'status': status, 'error_message': error_message}

        except ValueError as ve:
            logger.error(f"ValueError during Zarinpal payment verification: {ve}")
            return {'status': -101, 'error_message': str(ve)} 
        except Exception as e:
            logger.exception(f"Exception during Zarinpal payment verification: {e}")
            return {'status': -100, 'error_message': str(e)}
