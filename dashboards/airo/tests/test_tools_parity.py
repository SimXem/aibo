"""AIRO and the shared harness must execute the very same research tools."""
from fri_forecaster import tools
from redlines import tools as airo_tools


def test_airo_imports_shared_research_tools():
    assert airo_tools is tools
