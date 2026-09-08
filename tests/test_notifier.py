import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.delivery.notifier import send_telegram_report


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_telegram_report_sends_message_and_images(self):
        with (
            patch("macro_pulse.delivery.notifier.Bot") as bot_cls,
            patch("macro_pulse.delivery.notifier.os.path.exists", return_value=True),
            patch("builtins.open", unittest.mock.mock_open(read_data=b"image")),
        ):
            bot = AsyncMock()
            bot_cls.return_value = bot

            result = await send_telegram_report(
                "token",
                "chat-id",
                "hello",
                image_paths=["sample.png"],
                attempts=1,
            )

        self.assertTrue(result)
        bot.send_message.assert_awaited_once_with(chat_id="chat-id", text="hello")
        bot.send_photo.assert_awaited_once()

    async def test_photo_failure_retains_text_delivery_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "sent"
            photo = Path(folder) / "photo.png"
            photo.write_bytes(b"image")
            with patch("macro_pulse.delivery.notifier.Bot") as bot_cls:
                bot = AsyncMock()
                bot.send_photo.side_effect = RuntimeError("photo failed")
                bot_cls.return_value = bot
                result = await send_telegram_report(
                    "token",
                    "chat-id",
                    "hello",
                    image_paths=[str(photo)],
                    attempts=1,
                    delivery_receipt_path=receipt,
                )
            self.assertFalse(result)
            self.assertTrue(receipt.exists())
            bot.send_message.assert_awaited_once()

    async def test_text_failure_does_not_create_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "sent"
            with patch("macro_pulse.delivery.notifier.Bot") as bot_cls:
                bot = AsyncMock()
                bot.send_message.side_effect = RuntimeError("text failed")
                bot_cls.return_value = bot
                result = await send_telegram_report(
                    "token",
                    "chat-id",
                    "hello",
                    attempts=1,
                    delivery_receipt_path=receipt,
                )
            self.assertFalse(result)
            self.assertFalse(receipt.exists())
