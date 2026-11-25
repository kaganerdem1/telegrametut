from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def join_keyboard(joined_count=0):
    label = "🙋 Katıl" if joined_count == 0 else f"🙋 Katıl · {joined_count}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data="join")]
    ])