import sys
from datetime import datetime
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

def load_and_score(file_path: str = "assignments.csv") -> pd.DataFrame:
    try:
        df = pd.read_csv(file_path)
        if df.empty:
            raise pd.errors.EmptyDataError
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Could not find '{file_path}'.")
        sys.exit(1)
    except pd.errors.EmptyDataError:
        console.print(
            f"[bold red]Error:[/bold red] '{file_path}' is empty. "
            "Add at least one header row and task before running."
        )
        sys.exit(1)

    now = datetime.now()
    df["due_datetime"] = pd.to_datetime(df["due_date"])
    
    # Calculate days remaining (fractional)
    df["days_left"] = (df["due_datetime"] - now).dt.total_seconds() / 86400.0

    # Avoid division by zero for past-due/today tasks
    df["effective_days"] = df["days_left"].apply(lambda d: max(d, 0.25))

    # Triage prioritization metric
    df["triage_score"] = (
        df["grade_weight_pct"] * df["estimated_hours"]
    ) / df["effective_days"]

    # Sort descending by priority score
    df = df.sort_values(by="triage_score", ascending=False).reset_index(drop=True)
    return df

def render_terminal_ui(df: pd.DataFrame):
    table = Table(
        title="🎯 Daily Assignment Triage Engine",
        header_style="bold cyan",
        show_lines=True
    )

    table.add_column("Rank", justify="center", style="bold")
    table.add_column("Course", style="yellow")
    table.add_column("Task", style="white")
    table.add_column("Due Date", justify="center")
    table.add_column("Days Left", justify="right")
    table.add_column("Est. Hours", justify="right")
    table.add_column("Weight (%)", justify="right")
    table.add_column("Priority Score", justify="right", style="bold magenta")
    table.add_column("Status / Action", style="green")

    for i, row in df.iterrows():
        days = row["days_left"]
        
        # Color-code urgency
        if days < 1:
            urgency_str = f"[bold red]{days:.1f}d (Urgent)[/bold red]"
            action = "[bold red]Work Now[/bold red]"
        elif days < 3:
            urgency_str = f"[yellow]{days:.1f}d[/yellow]"
            action = "[yellow]Scheduled[/yellow]"
        else:
            urgency_str = f"[green]{days:.1f}d[/green]"
            action = "Backlog"

        table.add_row(
            str(i + 1),
            row["course"],
            row["task"],
            row["due_date"],
            urgency_str,
            f"{row['estimated_hours']:.1f}h",
            f"{row['grade_weight_pct']}%",
            f"{row['triage_score']:.1f}",
            action
        )

    console.print(table)

if __name__ == "__main__":
    df = load_and_score()
    render_terminal_ui(df)