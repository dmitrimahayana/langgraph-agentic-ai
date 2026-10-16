from typing import List
from src.tools.jira.Jira import jira_tools
from src.tools.slack.Slack import get_slack_tools

class ToolCatalog:
    def __init__(self):
        # Aggregate all tools from different sources
        # Jira tools are already a list of functions decorated with @tool
        # Slack tools are BaseTool instances from get_slack_tools()
        self._all_tools = {}
        
        # Register Jira tools
        for tool in jira_tools:
            self._all_tools[tool.name] = tool
            
        # Register Slack tools
        for tool in get_slack_tools():
            self._all_tools[tool.name] = tool

    def resolve(self, tool_names: List[str]):
        """
        Resolve requested tool names to their corresponding LangChain tool objects.
        
        Args:
            tool_names: List of tool names to resolve.
            
        Returns:
            List of resolved tool objects.
            
        Raises:
            ValueError: If any of the requested tool names are not found in the catalog.
        """
        resolved_tools = []
        for name in tool_names:
            if name not in self._all_tools:
                raise ValueError(f"Tool '{name}' not found in catalog. Available tools: {list(self._all_tools.keys())}")
            resolved_tools.append(self._all_tools[name])
            
        return resolved_tools

# Singleton instance for easy access
catalog = ToolCatalog()
