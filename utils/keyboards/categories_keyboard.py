from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_categories_keyboard(parent_id: int | None = None):
    """Return an InlineKeyboardMarkup for category browsing.

    Logic:
    1. If *parent_id* is None, we assume we need to show the first layer *under* the root
       category that has name starting with "🛒 محصولات".
    2. If the current *parent_id* has children, we list them.
    3. Back button behaviour:
       - If we are at the first layer (children of root) -> back goes to *main menu*.
       - Otherwise back goes up one level (parent's parent)."""

    from database.queries import DatabaseQueries as _DB

    # Resolve the "root products" category id dynamically so that we do not hard-code it.
    _ROOT_CAT = None
    roots = _DB.get_children_categories(None)
    for r in roots:
        if r["name"].startswith("🛒"):
            _ROOT_CAT = r["id"]
            break
    # If parent_id is None, we actually want to show children of the root products category.
    if parent_id is None and _ROOT_CAT is not None:
        parent_id = _ROOT_CAT

    categories = _DB.get_children_categories(parent_id)

    keyboard: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for cat in categories:
        cb_data = f"products_menu_{cat['id']}"
        row.append(InlineKeyboardButton(cat["name"], callback_data=cb_data))
        if len(row) == 2:  # two buttons per row
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # ---------------- Back button logic -----------------
    try:
        from utils.constants.all_constants import TEXT_GENERAL_BACK as _BACK_TXT
    except Exception:
        _BACK_TXT = "↩ بازگشت"

    # Determine back target and button text
    parent_cat = _DB.get_category_by_id(parent_id) if parent_id else None
    if parent_cat and parent_cat["parent_id"] is not None:
        # We are at 2+ depth -> back to parent level
        back_cb = f"products_menu_{parent_cat['parent_id']}" if parent_cat["parent_id"] else "products_menu"
    else:
        # We are at first layer under root -> back to main menu
        back_cb = "back_to_main_menu_from_categories"

    keyboard.append([InlineKeyboardButton("↩ بازگشت", callback_data=back_cb)])
    return InlineKeyboardMarkup(keyboard)
