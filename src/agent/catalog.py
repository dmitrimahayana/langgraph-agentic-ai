from typing import List, Optional
from src.tools.jira.Jira import jira_tools
from src.tools.tavily.Tavily import internet_tools
# from src.tools.slack.Slack import get_slack_tools

class ToolCatalog:
    def __init__(self):
        # Aggregate all tools from different sources
        # Jira tools are already a list of functions decorated with @tool
        # Slack tools are BaseTool instances from get_slack_tools()
        self._all_tools = {}
        
        # Register Jira tools
        for tool in jira_tools:
            self._all_tools[tool.name] = tool
        # register internet_tools
        for tool in internet_tools:
            self._all_tools[tool.name] = tool
            
        # Register Slack tools
        # for tool in get_slack_tools():
        #     self._all_tools[tool.name] = tool

    def resolve(self, tool_names: List[str], descriptions: Optional[dict[str, str]] = None):
        resolved_tools = []
        for name in tool_names:
            if name not in self._all_tools:
                raise ValueError(f"Tool '{name}' not found in catalog. Available tools: {list(self._all_tools.keys())}")
            
            tool = self._all_tools[name]
            
            # If a description override is provided for this tool, update it
            if descriptions and name in descriptions:
                tool.description = descriptions[name]
                
            resolved_tools.append(tool)
            
        return resolved_tools

# Singleton instance for easy access
catalog = ToolCatalog()

