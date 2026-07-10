"""web_search 工具测试。"""
from unittest.mock import MagicMock, patch

from vocamind.tools.web_search import run_web_search


@patch("vocamind.tools.web_search._search_duckduckgo")
def test_web_search_duckduckgo(mock_ddg):
    mock_ddg.return_value = [
        {"title": "Example", "url": "https://example.com", "snippet": "Hello world"},
    ]
    out = run_web_search("test query", max_results=3, backend="duckduckgo")
    assert "Example" in out
    assert "https://example.com" in out
    mock_ddg.assert_called_once_with("test query", 3)


@patch("vocamind.tools.web_search._search_tavily")
@patch("vocamind.tools.web_search._search_duckduckgo")
def test_web_search_tavily_fallback(mock_ddg, mock_tavily):
    mock_tavily.side_effect = RuntimeError("tavily down")
    mock_ddg.return_value = [
        {"title": "Fallback", "url": "https://fallback.test", "snippet": "ok"},
    ]
    out = run_web_search("news", backend="tavily")
    assert "Fallback" in out
    assert "duckduckgo (fallback)" in out


@patch.dict("os.environ", {}, clear=True)
def test_web_search_auto_uses_duckduckgo(mock_env=None):
    with patch("vocamind.tools.web_search._search_duckduckgo") as mock_ddg:
        mock_ddg.return_value = []
        out = run_web_search("empty", backend="auto")
        assert out.startswith("No results")
        mock_ddg.assert_called_once()


def test_web_search_empty_query():
    assert run_web_search("  ") == "Error: query 不能为空"
