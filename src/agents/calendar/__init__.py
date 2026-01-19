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

from .states import CalendarState, is_active_state
from .parsers import DateParser

# Lazy loaders - import functions, not classes
from .base_flow import CalendarFlowBase
from .view_flow import get_view_flow, ViewFlow
from .remove_flow import get_remove_flow, RemoveFlow
from .inline_add_flow import get_inline_add_flow, InlineAddFlow
from .add_flow import get_add_flow, AddFlow
from .scrape_flow import get_scrape_flow, ScrapeFlow

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

