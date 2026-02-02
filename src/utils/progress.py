from datetime import datetime, timezone
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.style import Style
from rich.text import Text
from typing import Dict, Optional, Callable, List

console = Console()


class AgentProgress:
    """Manages progress tracking for multiple agents."""

    def __init__(self):
        self.agent_status: Dict[str, Dict[str, str]] = {}
        self.table = Table(show_header=False, box=None, padding=(0, 1))
        self.live = Live(self.table, console=console, refresh_per_second=4)
        self.started = False
        self.update_handlers: List[Callable[[str, Optional[str], str], None]] = []

    def register_handler(self, handler: Callable[[str, Optional[str], str], None]):
        """Register a handler to be called when agent status updates."""
        self.update_handlers.append(handler)
        return handler  # Return handler to support use as decorator

    def unregister_handler(self, handler: Callable[[str, Optional[str], str], None]):
        """Unregister a previously registered handler."""
        if handler in self.update_handlers:
            self.update_handlers.remove(handler)

    def start(self):
        """Start the progress display."""
        if not self.started:
            # Reset agent status to clear stale data from previous runs
            self.reset()
            self.live.start()
            self.started = True

    def stop(self):
        """Stop the progress display."""
        if self.started:
            self.live.stop()
            self.started = False

    def reset(self):
        """Reset agent status to clear stale data from previous runs.
        
        This clears only the CLI display state (agent_status dict),
        not the update_handlers which may be needed for other purposes.
        """
        self.agent_status.clear()
        # Reset the table to clear any existing rows
        self.table = Table(show_header=False, box=None, padding=(0, 1))
        self.live.update(self.table)

    def update_status(self, agent_name: str, ticker: Optional[str] = None, status: str = "", analysis: Optional[str] = None):
        """Update the status of an agent."""
        if agent_name not in self.agent_status:
            self.agent_status[agent_name] = {"status": "", "ticker": None}

        if ticker:
            self.agent_status[agent_name]["ticker"] = ticker
        if status:
            self.agent_status[agent_name]["status"] = status
        if analysis:
            self.agent_status[agent_name]["analysis"] = analysis
        
        # Set the timestamp as UTC datetime
        timestamp = datetime.now(timezone.utc).isoformat()
        self.agent_status[agent_name]["timestamp"] = timestamp

        # Notify all registered handlers
        for handler in self.update_handlers:
            handler(agent_name, ticker, status, analysis, timestamp)

        self._refresh_display()

    def get_all_status(self):
        """Get the current status of all agents as a dictionary."""
        return {agent_name: {"ticker": info["ticker"], "status": info["status"], "display_name": self._get_display_name(agent_name)} for agent_name, info in self.agent_status.items()}

    def _get_display_name(self, agent_name: str) -> str:
        """Convert agent_name to a display-friendly format."""
        return agent_name.replace("_agent", "").replace("_", " ").title()

    def _refresh_display(self):
        """Refresh the progress display."""
        self.table.columns.clear()
        self.table.add_column(width=120)

        # Sort agents with Risk Management and Portfolio Management at the bottom
        def sort_key(item):
            agent_name = item[0]
            if "risk_management" in agent_name:
                return (2, agent_name)
            elif "portfolio_management" in agent_name:
                return (3, agent_name)
            else:
                return (1, agent_name)

        for agent_name, info in sorted(self.agent_status.items(), key=sort_key):
            status = info["status"]
            ticker = info["ticker"]
            analysis = info.get("analysis", "")
            
            # Create the status text with appropriate styling
            # Use ASCII symbols for Windows compatibility
            if status.lower() == "done":
                style = Style(color="green", bold=True)
                symbol = "[OK]"
                # Add analysis summary if available
                if analysis:
                    # Truncate to 60 chars for display alignment
                    truncated_analysis = analysis[:60] + "..." if len(analysis) > 60 else analysis
                    display_status = f"Done - {truncated_analysis}"
                else:
                    display_status = status
            elif status.lower() == "error":
                style = Style(color="red", bold=True)
                symbol = "[X]"
                display_status = status
            else:
                style = Style(color="yellow")
                symbol = "..."
                display_status = status

            agent_display = self._get_display_name(agent_name)
            status_text = Text()
            status_text.append(f"{symbol} ", style=style)
            status_text.append(f"{agent_display:<20}", style=Style(bold=True))

            if ticker:
                status_text.append(f"[{ticker}] ", style=Style(color="cyan"))
            status_text.append(display_status, style=style)

            self.table.add_row(status_text)


# Create a global instance
progress = AgentProgress()
