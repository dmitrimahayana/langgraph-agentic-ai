import os
from typing import Optional, Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


# ---------- Shared client + fixed channel ----------
def get_slack_client() -> WebClient:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN environment variable not set")
    return WebClient(token=token)

SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
if not SLACK_CHANNEL_ID:
    raise ValueError("SLACK_CHANNEL_ID environment variable not set")


# ---------- 1. Send Message ----------
class SlackSendMessageInput(BaseModel):
    message: str = Field(description="Text content of the message to send")
    thread_ts: Optional[str] = Field(
        default=None, description="Timestamp of parent message to reply in thread"
    )


class SlackSendMessageTool(BaseTool):
    name: str = "slack_send_message"
    description: str = (
        "Send a message to the team's Slack channel. "
        "Input requires 'message', optionally 'thread_ts' to reply in a thread."
    )
    args_schema: Type[BaseModel] = SlackSendMessageInput

    def _run(self, message: str, thread_ts: Optional[str] = None) -> str:
        client = get_slack_client()
        try:
            response = client.chat_postMessage(
                channel=SLACK_CHANNEL_ID, text=message, thread_ts=thread_ts
            )
            return f"Message sent successfully. ts={response['ts']}"
        except SlackApiError as e:
            return f"Error sending message: {e.response['error']}"


# ---------- 2. Read Channel History ----------
class SlackReadHistoryInput(BaseModel):
    limit: int = Field(default=10, description="Number of recent messages to fetch")


class SlackReadHistoryTool(BaseTool):
    name: str = "slack_read_history"
    description: str = (
        "Read recent message history from the team's Slack channel. "
        "Input optionally takes 'limit' (default 10)."
    )
    args_schema: Type[BaseModel] = SlackReadHistoryInput

    def _run(self, limit: int = 10) -> str:
        client = get_slack_client()
        try:
            response = client.conversations_history(channel=SLACK_CHANNEL_ID, limit=limit)
            messages = response.get("messages", [])
            if not messages:
                return "No messages found."
            formatted = []
            for m in messages:
                user = m.get("user", "unknown")
                text = m.get("text", "")
                ts = m.get("ts", "")
                formatted.append(f"[{ts}] {user}: {text}")
            return "\n".join(formatted)
        except SlackApiError as e:
            return f"Error reading history: {e.response['error']}"


# ---------- 3. Reply in Thread (convenience wrapper) ----------
class SlackReplyThreadInput(BaseModel):
    thread_ts: str = Field(description="Timestamp of the parent message to reply to")
    message: str = Field(description="Reply text")


class SlackReplyThreadTool(BaseTool):
    name: str = "slack_reply_thread"
    description: str = "Reply to a specific thread in the team's Slack channel."
    args_schema: Type[BaseModel] = SlackReplyThreadInput

    def _run(self, thread_ts: str, message: str) -> str:
        client = get_slack_client()
        try:
            response = client.chat_postMessage(
                channel=SLACK_CHANNEL_ID, text=message, thread_ts=thread_ts
            )
            return f"Reply sent. ts={response['ts']}"
        except SlackApiError as e:
            return f"Error sending reply: {e.response['error']}"


# ---------- Collect tools ----------
def get_slack_tools():
    return [
        SlackSendMessageTool(),
        SlackReadHistoryTool(),
        SlackReplyThreadTool(),
    ]