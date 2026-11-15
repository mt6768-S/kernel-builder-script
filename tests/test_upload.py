import pathlib
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


@patch("kbuild.upload.gofile.GoFileUploader.upload_file")
@patch("requests.post")
def test_telegram_large_file_fallback_gofile(mock_post, mock_gofile, tmp_path):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_post.return_value = mock_resp
    mock_gofile.return_value = "https://gofile.io/d/abc123"

    large_file = tmp_path / "large_kernel.zip"
    large_file.write_text("LARGE", encoding="utf-8")

    # Patch stat size to 50 MB
    with patch.object(
        pathlib.Path, "stat", return_value=MagicMock(st_size=50 * 1024 * 1024)
    ):
        tg = TelegramUploader("123:ABC", "-100123")
        assert tg.upload_document(large_file, caption="Build Success") is True

    mock_gofile.assert_called_once_with(large_file)
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["data"]
    assert "https://gofile.io/d/abc123" in payload["text"]
    assert "exceeds Telegram limit" in payload["text"]


@patch("kbuild.upload.gofile.GoFileUploader.upload_file")
@patch("requests.post")
def test_telegram_file_too_big_400_fallback(mock_post, mock_gofile, tmp_path):
    # First call (sendDocument) returns 400 "file is too big", second call (sendMessage) returns 200
    resp_doc = MagicMock()
    resp_doc.status_code = 400
    resp_doc.text = "Bad Request: file is too big"

    resp_msg = MagicMock()
    resp_msg.status_code = 200
    resp_msg.json.return_value = {"ok": True}

    mock_post.side_effect = [resp_doc, resp_msg]
    mock_gofile.return_value = "https://gofile.io/d/fallback400"

    test_file = tmp_path / "test.zip"
    test_file.write_text("DATA", encoding="utf-8")

    tg = TelegramUploader("123:ABC", "-100123")
    assert tg.upload_document(test_file, caption="Build Success") is True
    mock_gofile.assert_called_once_with(test_file)
    assert mock_post.call_count == 2
