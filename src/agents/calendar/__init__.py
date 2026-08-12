"""
Calendar Agent Submodules - Modular Architecture for Lazy Loading.

This package provides decomposed flow handlers for the calendar agent:
- states.py: CalendarState enum for session state machine
- parsers.py: DateParser for inline date parsing
- base_flow.py: Common utilities for all flows
- view_flow.py: Handler for viewing events
- remove_flow.py: Handler for removing events
- inline_add_flow.py: Handler for inline add syntax
- add_flow.py: Handler for interactive add flow
- scrape_flow.py: Handler for message scraping flow

All flow handlers use lazy loading for on-demand instantiation.
"""

from .add_flow import AddFlow, get_add_flow

# Lazy loaders - import functions, not classes
from .base_flow import CalendarFlowBase
from .inline_add_flow import InlineAddFlow, get_inline_add_flow
from .parsers import DateParser
from .remove_flow import RemoveFlow, get_remove_flow
from .scrape_flow import ScrapeFlow, get_scrape_flow
from .states import CalendarState, is_active_state
from .view_flow import ViewFlow, get_view_flow

__all__ = [
    # States
    "CalendarState",
    "is_active_state",
    # Parsers
    "DateParser",
    # Base
    "CalendarFlowBase",
    # Flows
    "ViewFlow",
    "get_view_flow",
    "RemoveFlow",
    "get_remove_flow",
    "InlineAddFlow",
    "get_inline_add_flow",
    "AddFlow",
    "get_add_flow",
    "ScrapeFlow",
    "get_scrape_flow",
]
