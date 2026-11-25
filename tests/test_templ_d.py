from fractions import Fraction

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from embykeeper.telegram.checkiner._templ_d import find_answer_button, solve_math_expression


def challenge(text, buttons):
    return Message(
        id=1,
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(str(value), callback_data=str(value)) for value in buttons]]
        ),
    )


def test_solves_screenshot_challenge_and_finds_button():
    message = challenge("🎯 签到验证\n\n3 - 3 = ?", [3, 0, 9, 8])

    answer = solve_math_expression(message.text)

    assert answer == Fraction(0)
    assert find_answer_button(message, answer) == "0"


def test_supports_common_operators_and_full_width_characters():
    assert solve_math_expression("12 + 7 = ?") == 19
    assert solve_math_expression("6 × 7 = ?") == 42
    assert solve_math_expression("８ ÷ ４ ＝ ？") == 2
    assert solve_math_expression("3 - -2 = ?") == 5


def test_requires_an_exact_numeric_answer_button():
    message = challenge("签到验证\n5 / 2 = ?", ["2", "2.5 points", "3"])

    assert find_answer_button(message, Fraction(5, 2)) is None


def test_rejects_non_challenge_text_and_division_by_zero():
    assert solve_math_expression("balance: 3 - 3") is None
    assert solve_math_expression("3 / 0 = ?") is None
