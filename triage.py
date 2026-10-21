import argparse
import sys
import uuid
from datetime import datetime, date, time, timedelta
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()
CSV_PATH = "assignments.csv"
COLUMNS = ["course", "task", "due_date", "grade_weight_pct", "estimated_hours"]


def load_raw_data(file_path: str = CSV_PATH) -> pd.DataFrame:
    try:
        df = pd.read_csv(file_path)
        if df.empty:
            return pd.DataFrame(columns=COLUMNS)
        return df
    except (FileNotFoundError, pd.errors.EmptyDataError):
        df = pd.DataFrame(columns=COLUMNS)
        df.to_csv(file_path, index=False)
        return df


def save_data(df: pd.DataFrame, file_path: str = CSV_PATH) -> None:
    df[COLUMNS].to_csv(file_path, index=False)


def compute_scored_df(file_path: str = CSV_PATH) -> pd.DataFrame:
    df = load_raw_data(file_path)
    if df.empty:
        return df

    now = datetime.now()
    df["due_datetime"] = pd.to_datetime(df["due_date"])
    df["days_left"] = (df["due_datetime"] - now).dt.total_seconds() / 86400.0
    df["effective_days"] = df["days_left"].apply(lambda d: max(d, 0.25))

    df["triage_score"] = (
        df["grade_weight_pct"] * df["estimated_hours"]
    ) / df["effective_days"]

    df["orig_index"] = df.index
    return df.sort_values(by="triage_score", ascending=False).reset_index(drop=True)


def list_assignments(file_path: str = CSV_PATH) -> None:
    df = compute_scored_df(file_path)
    if df.empty:
        console.print("[yellow]No pending assignments found. Add one with 'add'![/yellow]")
        return

    table = Table(
        title="🎯 Daily Assignment Triage Engine",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("ID", justify="center", style="bold dim")
    table.add_column("Rank", justify="center", style="bold")
    table.add_column("Course", style="yellow")
    table.add_column("Task", style="white")
    table.add_column("Due Date", justify="center")
    table.add_column("Days Left", justify="right")
    table.add_column("Est. Hours", justify="right")
    table.add_column("Weight (%)", justify="right")
    table.add_column("Score", justify="right", style="bold magenta")
    table.add_column("Urgency", style="green")

    for rank, row in df.iterrows():
        days = row["days_left"]
        if days < 1:
            urgency = "[bold red]Work Now (<1d)[/bold red]"
            days_str = f"[bold red]{days:.1f}d[/bold red]"
        elif days < 3:
            urgency = "[yellow]Scheduled (<3d)[/yellow]"
            days_str = f"[yellow]{days:.1f}d[/yellow]"
        else:
            urgency = "Backlog"
            days_str = f"[green]{days:.1f}d[/green]"

        table.add_row(
            str(row["orig_index"]),
            str(rank + 1),
            str(row["course"]),
            str(row["task"]),
            str(row["due_date"]),
            days_str,
            f"{row['estimated_hours']:.1f}h",
            f"{row['grade_weight_pct']}%",
            f"{row['triage_score']:.1f}",
            urgency,
        )

    console.print(table)
    console.print("[dim]Use the ID column with 'python triage.py done <ID>' to complete tasks.[/dim]\n")


def add_assignment(course: str, task: str, due: str, weight: float, hours: float) -> None:
    try:
        datetime.strptime(due, "%Y-%m-%d")
    except ValueError:
        console.print("[bold red]Error:[/bold red] Date must be in YYYY-MM-DD format (e.g. 2026-10-28).")
        sys.exit(1)

    df = load_raw_data()
    new_entry = pd.DataFrame([{
        "course": course.strip(),
        "task": task.strip(),
        "due_date": due.strip(),
        "grade_weight_pct": float(weight),
        "estimated_hours": float(hours),
    }])
    df = pd.concat([df, new_entry], ignore_index=True)
    save_data(df)
    console.print(f"[bold green]✓ Added:[/bold green] {task} ({course}) due {due}")


def remove_assignment(task_id: int) -> None:
    df = load_raw_data()
    if task_id not in df.index:
        console.print(f"[bold red]Error:[/bold red] ID {task_id} not found. Run 'python triage.py list' to view valid IDs.")
        sys.exit(1)

    completed = df.loc[task_id]
    df = df.drop(index=task_id).reset_index(drop=True)
    save_data(df)
    console.print(f"[bold green]✓ Completed & Removed:[/bold green] {completed['task']} ({completed['course']})")


def format_ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def export_calendar(
    output_path: str = "study_schedule.ics",
    start_hour: int = 14,
    max_daily_hours: float = 4.0,
    block_duration_min: int = 90,
) -> None:
    df = compute_scored_df()
    if df.empty:
        console.print("[yellow]No tasks to export.[/yellow]")
        return

    now = datetime.now()
    schedule_date = now.date() if now.hour < 20 else now.date() + timedelta(days=1)
    current_time_slot = datetime.combine(schedule_date, time(hour=start_hour, minute=0))
    if current_time_slot < now:
        current_time_slot = (now + timedelta(minutes=15)).replace(second=0, microsecond=0)

    daily_study_logged = 0.0
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Assignment Triage Engine//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Assignment Focus Schedule",
    ]

    for _, row in df.iterrows():
        clean_due = row["due_date"].replace("-", "")
        due_next_day = (datetime.strptime(row["due_date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        uid = f"deadline-{uuid.uuid4()}@triage-engine"

        ics_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{format_ics_dt(now)}",
            f"DTSTART;VALUE=DATE:{clean_due}",
            f"DTEND;VALUE=DATE:{due_next_day}",
            f"SUMMARY:🚨 DEADLINE: {row['course']} - {row['task']}",
            f"DESCRIPTION:Grade Weight: {row['grade_weight_pct']}% | Priority Score: {row['triage_score']:.1f}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    total_scheduled_blocks = 0
    for _, row in df.iterrows():
        remaining_minutes = int(float(row["estimated_hours"]) * 60)
        chunk_idx = 1

        while remaining_minutes > 0:
            if daily_study_logged >= max_daily_hours or current_time_slot.hour >= 21:
                schedule_date += timedelta(days=1)
                current_time_slot = datetime.combine(schedule_date, time(hour=start_hour, minute=0))
                daily_study_logged = 0.0

            session_duration = min(remaining_minutes, block_duration_min)
            session_end = current_time_slot + timedelta(minutes=session_duration)

            uid = f"focus-{uuid.uuid4()}@triage-engine"
            summary = f"📚 Focus: {row['course']} - {row['task']} (Pt {chunk_idx})"
            description = (
                f"Task: {row['task']}\\n"
                f"Course: {row['course']}\\n"
                f"Grade Weight: {row['grade_weight_pct']}%\\n"
                f"Triage Priority: {row['triage_score']:.1f}\\n"
                f"Due: {row['due_date']}"
            )

            ics_lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{format_ics_dt(now)}",
                f"DTSTART:{format_ics_dt(current_time_slot)}",
                f"DTEND:{format_ics_dt(session_end)}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ])

            total_scheduled_blocks += 1
            chunk_idx += 1
            remaining_minutes -= session_duration
            daily_study_logged += session_duration / 60.0
            current_time_slot = session_end + timedelta(minutes=15)

    ics_lines.append("END:VCALENDAR")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(ics_lines) + "\r\n")

    console.print(f"[bold green]✓ Exported {total_scheduled_blocks} study blocks and {len(df)} deadlines to '{output_path}'![/bold green]")
    console.print("[dim]Double-click the .ics file on macOS or import it into Google Calendar / Apple Calendar.[/dim]\n")


def main():
    parser = argparse.ArgumentParser(
        description="Smart Assignment Triage Engine CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="Display prioritized assignments")

    add_parser = subparsers.add_parser("add", help="Add a new assignment")
    add_parser.add_argument("--course", "-c", required=True, help="Course name (e.g., 'STATS 100A')")
    add_parser.add_argument("--task", "-t", required=True, help="Task description")
    add_parser.add_argument("--due", "-d", required=True, help="Due date in YYYY-MM-DD")
    add_parser.add_argument("--weight", "-w", type=float, required=True, help="Grade weight %% (e.g., 15)")
    add_parser.add_argument("--hours", type=float, required=True, help="Estimated work hours (e.g., 4.5)")

    done_parser = subparsers.add_parser("done", help="Mark an assignment as completed")
    done_parser.add_argument("id", type=int, help="Assignment ID from the ID column in 'list'")

    ics_parser = subparsers.add_parser("export-ics", help="Generate .ics calendar with scheduled focus blocks")
    ics_parser.add_argument("--output", "-o", default="study_schedule.ics", help="Output file path")
    ics_parser.add_argument("--start-hour", "-s", type=int, default=14, help="Starting hour of study window (24h format, e.g. 14 for 2 PM)")
    ics_parser.add_argument("--max-daily", "-m", type=float, default=4.0, help="Max study hours scheduled per day")

    args = parser.parse_args()

    if args.command == "add":
        add_assignment(args.course, args.task, args.due, args.weight, args.hours)
    elif args.command == "done":
        remove_assignment(args.id)
    elif args.command == "export-ics":
        export_calendar(
            output_path=args.output,
            start_hour=args.start_hour,
            max_daily_hours=args.max_daily,
        )
    else:
        list_assignments()


if __name__ == "__main__":
    main()
