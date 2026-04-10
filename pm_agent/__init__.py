"""
pm_agent — Project Manager Agent for Financial_Tools.

Scans the codebase for TODOs and stubs, builds a work breakdown structure,
and creates GitHub Issues + Project boards so specialized agents can pick up
and implement tasks.

Usage:
    python -m pm_agent --dry-run          # preview without touching GitHub
    python -m pm_agent                    # create issues + project board
    python -m pm_agent --scan-only        # just print the WBS
"""
