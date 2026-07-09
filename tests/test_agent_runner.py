"""Agent runner 测试。"""
from threading import Event
from unittest.mock import MagicMock, patch

from vocamind.agent.runner import agent_loop_for_task
from vocamind.agent.state import AgentRuntime
from vocamind.common.config import PipelineConfig
from vocamind.status import StatusRegistry
from vocamind.tasks.queue import AgentTaskMessage, AgentTaskQueue


@patch.dict("os.environ", {"AGENT_LLM_API_KEY": "test"})
@patch("vocamind.agent.runner.call_agent_llm")
@patch("vocamind.agent.runner.setup_agent_tools")
def test_agent_loop_completes_without_tools(mock_setup, mock_call_llm):
    mock_setup.return_value = ([], {})
    assistant = MagicMock()
    assistant.content = "Done with task"
    assistant.tool_calls = None
    response = MagicMock()
    response.choices = [MagicMock(message=assistant, finish_reason="stop")]
    mock_call_llm.return_value = response

    stop = Event()
    queue = AgentTaskQueue()
    registry = StatusRegistry()
    runtime = AgentRuntime(stop_event=stop, task_queue=queue, status_registry=registry)
    config = PipelineConfig()

    from vocamind.llm.tool_client import ToolCallingClient

    client = ToolCallingClient(model="test", api_url=None, api_key_env="AGENT_LLM_API_KEY")
    task_msg = AgentTaskMessage(
        task_id="task_test",
        subject="Test",
        description="Do something",
        source="voice",
    )

    with patch("vocamind.agent.runner.claim_task"), patch("vocamind.agent.runner.fail_task") as mock_fail:
        summary = agent_loop_for_task(runtime, client, config, task_msg)

    assert "Done" in summary
    mock_fail.assert_not_called()
