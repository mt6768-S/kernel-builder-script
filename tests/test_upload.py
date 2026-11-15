import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import BadRequest, TelegramError

from kbuild.upload.telegram import TelegramUploader


class FakeBot:
    def __init__(self, token):
        self.token = token
        self.send_message = AsyncMock()
        self.send_document = AsyncMock()
        self.send_media_group = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _bot_mock():
    return FakeBot("test-token")


def test_telegram_send_message():
    bot = _bot_mock()

    with patch("kbuild.upload.telegram.Bot", return_value=bot):
        tg = TelegramUploader("123:ABC", "-100123")
        assert tg.is_configured is True
        assert tg.send_message("<b>Test message</b>") is True

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == "-100123"
    assert bot.send_message.await_args.kwargs["text"] == "<b>Test message</b>"


def test_telegram_unconfigured():
    tg = TelegramUploader("", "")
    assert tg.is_configured is False
    assert tg.send_message("Test") is False


def test_telegram_upload_document(tmp_path):
    bot = _bot_mock()

    test_file = tmp_path / "test.zip"
    test_file.write_text("DATA", encoding="utf-8")

    with patch("kbuild.upload.telegram.Bot", return_value=bot):
        tg = TelegramUploader("123:ABC", "-100123")
        assert tg.upload_document(test_file, caption="Test caption") is True

    bot.send_document.assert_awaited_once()
    kwargs = bot.send_document.await_args.kwargs
    assert kwargs["filename"] == "test.zip"
    assert kwargs["caption"] == "Test caption"


def test_telegram_media_group_upload(tmp_path):
    bot = _bot_mock()

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    first.write_text("A", encoding="utf-8")
    second.write_text("B", encoding="utf-8")

    with patch("kbuild.upload.telegram.Bot", return_value=bot):
        tg = TelegramUploader("123:ABC", "-100123")
        assert tg.upload_documents([first, second], caption="Artifacts") is True

    bot.send_media_group.assert_awaited_once()
    bot.send_document.assert_not_awaited()


def test_telegram_media_group_failure_falls_back(tmp_path):
    bot = _bot_mock()
    bot.send_media_group.side_effect = TelegramError("boom")

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    first.write_text("A", encoding="utf-8")
    second.write_text("B", encoding="utf-8")

    with patch("kbuild.upload.telegram.Bot", return_value=bot):
        tg = TelegramUploader("123:ABC", "-100123")
        assert tg.upload_documents([first, second], caption="Artifacts") is True

    bot.send_media_group.assert_awaited_once()
    assert bot.send_document.await_count == 2


@patch("kbuild.upload.gofile.GoFileUploader.upload_file")
def test_telegram_large_file_fallback_gofile(mock_gofile, tmp_path):
    bot = _bot_mock()
    mock_gofile.return_value = "https://gofile.io/d/abc123"

    large_file = tmp_path / "large_kernel.zip"
    large_file.write_text("LARGE", encoding="utf-8")

    with patch.object(
        pathlib.Path, "stat", return_value=MagicMock(st_size=50 * 1024 * 1024)
    ):
        with patch("kbuild.upload.telegram.Bot", return_value=bot):
            tg = TelegramUploader("123:ABC", "-100123")
            assert tg.upload_document(large_file, caption="Build Success") is True

    mock_gofile.assert_called_once_with(large_file)
    bot.send_document.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    text = bot.send_message.await_args.kwargs["text"]
    assert "Build Success" in text
    assert "https://gofile.io/d/abc123" in text


def test_gofile_link_included_in_document_caption(tmp_path):
    bot = _bot_mock()

    test_file = tmp_path / "test.zip"
    test_file.write_text("DATA", encoding="utf-8")

    with patch("kbuild.upload.telegram.Bot", return_value=bot):
        tg = TelegramUploader("123:ABC", "-100123")
        assert (
            tg.upload_document(
                test_file,
                caption="Build Success",
                gofile_url="https://gofile.io/d/inline",
            )
            is True
        )

    caption = bot.send_document.await_args.kwargs["caption"]
    assert "Build Success" in caption
    assert "https://gofile.io/d/inline" in caption


def test_caption_preserves_literal_html_like_text(tmp_path):
    bot = _bot_mock()
    test_file = tmp_path / "test.zip"
    test_file.write_text("DATA", encoding="utf-8")

    with patch("kbuild.upload.telegram.Bot", return_value=bot):
        tg = TelegramUploader("123:ABC", "-100123")
        assert tg.upload_document(test_file, caption="commit: <vrdons>") is True

    assert bot.send_document.await_args.kwargs["caption"] == "commit: <vrdons>"


def test_telegram_file_too_big_400_fallback(tmp_path):
    bot = _bot_mock()
    bot.send_document.side_effect = BadRequest("Bad Request: file is too big")

    test_file = tmp_path / "test.zip"
    test_file.write_text("DATA", encoding="utf-8")

    with patch(
        "kbuild.upload.gofile.GoFileUploader.upload_file",
        return_value="https://gofile.io/d/fallback400",
    ):
        with patch("kbuild.upload.telegram.Bot", return_value=bot):
            tg = TelegramUploader("123:ABC", "-100123")
            assert tg.upload_document(test_file, caption="Build Success") is True

    assert bot.send_document.await_count == 1
    bot.send_message.assert_awaited_once()
    assert (
        "https://gofile.io/d/fallback400" in bot.send_message.await_args.kwargs["text"]
    )


def test_telegram_chat_id_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100999888")
    tg = TelegramUploader("123:ABC", "-100123")
    assert tg.chat_id == "-100999888"


def test_telegram_chat_id_from_short_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("CHAT_ID", "-100777666")
    tg = TelegramUploader("123:ABC", "")
    assert tg.chat_id == "-100777666"
