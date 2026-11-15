from unittest.mock import MagicMock, patch

from kbuild.upload.telegram import TelegramUploader


@patch("requests.post")
def test_telegram_send_message(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_post.return_value = mock_resp

    tg = TelegramUploader("123:ABC", "-100123")
    assert tg.is_configured is True
    assert tg.send_message("<b>Test message</b>") is True
    mock_post.assert_called_once()


def test_telegram_unconfigured():
    tg = TelegramUploader("", "")
    assert tg.is_configured is False
    assert tg.send_message("Test") is False


@patch("requests.post")
def test_telegram_upload_document(mock_post, tmp_path):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_post.return_value = mock_resp

    test_file = tmp_path / "test.zip"
    test_file.write_text("DATA", encoding="utf-8")

    tg = TelegramUploader("123:ABC", "-100123")
    assert tg.upload_document(test_file, caption="Test caption") is True
