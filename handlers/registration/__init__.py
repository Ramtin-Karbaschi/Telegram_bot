"""
Registration handlers package initialization
"""

from handlers.registration.registration_handlers import (
    # Handler functions
    start_registration, 
    get_phone, 
    get_fullname, 
    get_birthyear, 
    get_education,
    get_occupation,
    cancel_registration,
    # Conversation states
    REGISTRATION_START,
    GET_PHONE,
    GET_FULLNAME,
    GET_BIRTHYEAR,
    GET_EDUCATION,
    GET_OCCUPATION,
    # SHOW_PLANS, # Removed as it's no longer part of the simplified registration flow
    # Conversation handler
    registration_conversation
)

__all__ = [
    'start_registration', 
    'get_phone', 
    'get_fullname', 
    'get_birthyear', 
    'get_education',
    'get_occupation',
    'cancel_registration',
    'REGISTRATION_START',
    'GET_PHONE',
    'GET_FULLNAME',
    'GET_BIRTHYEAR',
    'GET_EDUCATION',
    'GET_OCCUPATION',
    # 'SHOW_PLANS', # Removed as it's no longer defined
    'registration_conversation'  # Added this line
]
