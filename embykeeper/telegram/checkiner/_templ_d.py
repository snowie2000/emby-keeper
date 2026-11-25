import asyncio
from fractions import Fraction
import operator
import random
import re
from typing import List, Optional, Union

from pydantic import ValidationError
from pyrogram.errors import MessageIdInvalid
from pyrogram.raw.types.messages import BotCallbackAnswer
from pyrogram.types import InlineKeyboardMarkup, Message

from embykeeper.utils import to_iterable

from ._templ_a import TemplateACheckin, TemplateACheckinConfig

__ignore__ = True


_EXPRESSION_PATTERN = re.compile(
    r"(?<![\d.])(?P<left>-?\d+)\s*(?P<operator>[+\-*/xX×÷−])\s*" r"(?P<right>-?\d+)\s*=\s*[?？]"
)
_NUMBER_PATTERN = re.compile(r"^[+\-]?\d+(?:\.\d+)?$")
_NORMALIZE = str.maketrans(
    "０１２３４５６７８９＋－＊／．＝？−×÷",
    "0123456789+-*/.=?-*/",
)
_OPERATORS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "x": operator.mul,
}


def solve_math_expression(text: str) -> Optional[Fraction]:
    """Extract and solve the simple arithmetic expression used by check-in challenges."""
    match = _EXPRESSION_PATTERN.search(text.translate(_NORMALIZE))
    if not match:
        return None

    left = Fraction(match.group("left"))
    right = Fraction(match.group("right"))
    operation = _OPERATORS[match.group("operator").lower()]
    if operation is operator.truediv and not right:
        return None
    return operation(left, right)


def find_answer_button(message: Message, answer: Fraction) -> Optional[str]:
    """Return the exact numeric button label matching *answer*, if one exists."""
    markup = message.reply_markup
    if not isinstance(markup, InlineKeyboardMarkup):
        return None

    for row in markup.inline_keyboard:
        for button in row:
            label = button.text.strip()
            normalized = label.translate(_NORMALIZE)
            if _NUMBER_PATTERN.fullmatch(normalized) and Fraction(normalized) == answer:
                return label
    return None


class TemplateDCheckinConfig(TemplateACheckinConfig):
    # fmt: off
    verification_keywords: Union[str, List[str]] = ["签到验证", "簽到驗證", "check-in verification", "checkin verification"]  # 算术验证消息关键词; 置空则只根据算式和数字按钮判断
    verification_click_delay: float = 1.0  # 点击验证答案前的最长随机等待秒数
    # fmt: on


class TemplateDCheckin(TemplateACheckin):
    """Template A check-in flow with deterministic inline math verification."""

    async def init(self):
        if not await super().init():
            return False
        try:
            self.d_config = TemplateDCheckinConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"初始化失败: 签到自定义模板 D 的配置错误:\n{e}")
            return False

        self.verification_keywords = self.d_config.verification_keywords
        self.verification_click_delay = self.d_config.verification_click_delay
        self._verification_messages = set()
        self._verification_lock = asyncio.Lock()
        return True

    async def message_handler(self, client, message: Message):
        if await self.handle_math_verification(message):
            return
        await super().message_handler(client, message)

    async def handle_math_verification(self, message: Message) -> bool:
        text = message.text or message.caption
        if not text:
            return False

        keywords = to_iterable(self.verification_keywords)
        if keywords and not any(keyword.lower() in text.lower() for keyword in keywords):
            return False

        answer = solve_math_expression(text)
        if answer is None:
            return False

        button = find_answer_button(message, answer)
        if button is None:
            self.log.warning("签到失败: 检测到算术验证, 但未找到正确答案按钮.")
            await self.fail()
            return True

        # Telegram can deliver the original message and its edit nearly together.
        # Claim the message before sleeping so the callback is never submitted twice.
        message_key = (getattr(message.chat, "id", None), message.id)
        async with self._verification_lock:
            if message_key in self._verification_messages:
                return True
            self._verification_messages.add(message_key)

        self.log.debug(f"[gray50]检测到算术验证, 将选择答案: {button}.[/]")
        if self.verification_click_delay > 0:
            await asyncio.sleep(random.uniform(0, self.verification_click_delay))
        try:
            callback_answer: BotCallbackAnswer = await message.click(button)
        except TimeoutError:
            self.log.debug("点击验证答案无响应, 可能按钮未正确处理点击回复.")
        except MessageIdInvalid:
            pass
        else:
            await self.on_button_answer(callback_answer)
        return True


def use(**kw):
    return type("TemplatedClass", (TemplateDCheckin,), kw)
