from langchain_community.tools.tavily_search import TavilySearchResults

def get_search_tool():
    global _search_tool
    if _search_tool is None:
        _search_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
        )
    return _search_tool

internet_tools = [get_search_tool()]