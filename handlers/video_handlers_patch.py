# Video Management Callback Handlers to be added to conversation handlers

# For ADD_PLAN conversation handler FIELD_VALUE state, add these lines before MessageHandler:
ADD_PLAN_VIDEO_HANDLERS = """
                      CallbackQueryHandler(self._handle_manage_video_captions, pattern='^manage_video_captions$'),
                      CallbackQueryHandler(self._handle_video_help, pattern='^video_help$'),
                      CallbackQueryHandler(self._handle_force_confirm_videos, pattern='^force_confirm_videos$'),
                      CallbackQueryHandler(self._handle_back_to_video_selection, pattern='^back_to_video_selection$'),
"""

# For EDIT_PLAN conversation handler FIELD_VALUE state, add these lines before MessageHandler:
EDIT_PLAN_VIDEO_HANDLERS = """
                      CallbackQueryHandler(self._handle_manage_video_captions, pattern='^manage_video_captions$'),
                      CallbackQueryHandler(self._handle_video_help, pattern='^video_help$'),
                      CallbackQueryHandler(self._handle_force_confirm_videos, pattern='^force_confirm_videos$'),
                      CallbackQueryHandler(self._handle_back_to_video_selection, pattern='^back_to_video_selection$'),
"""

# Instructions:
# 1. In line ~2233 (ADD_PLAN FIELD_VALUE state), add ADD_PLAN_VIDEO_HANDLERS before MessageHandler
# 2. In line ~2271 (EDIT_PLAN FIELD_VALUE state), add EDIT_PLAN_VIDEO_HANDLERS before MessageHandler
