"""Command-line GroupMe client.

Provides commands to interact with GroupMe groups and direct messages.

Usage examples:
    python main.py list-groups
    python main.py read 123456789 --limit 50
    python main.py send 123456789 "Hello Group!" --dry-run
    python main.py dm 987654321 "Hey there" --dry-run
    python main.py list-dms

Environment:
    GROUPME_TOKEN must be set (can be loaded from .env file).
"""
from __future__ import annotations

import os
import sys
import datetime as dt
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel
from rich.prompt import Confirm
from dotenv import load_dotenv

from groupme_api import build_client_from_env, GroupMeAPIError
from utils import watch_group, export_group_messages, stats_from_messages
import asyncio
import json
import csv
from pathlib import Path
import uvicorn

app = typer.Typer(add_completion=False, help="GroupMe CLI")
console = Console()

# Load .env early.
load_dotenv()


def _format_ts(epoch_seconds: int | float | None) -> str:
    if epoch_seconds is None:
        return "-"
    try:
        # GroupMe timestamps are in epoch seconds (ints). Convert to local timezone.
        dt_obj = dt.datetime.fromtimestamp(float(epoch_seconds))
        return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(epoch_seconds)


@app.command("list-groups")
def list_groups() -> None:
    """List all groups for the authenticated user."""
    try:
        client = build_client_from_env()
        groups = client.list_all_groups()
    except GroupMeAPIError as e:
        console.print(f"[red]Error listing groups:[/red] {e}")
        raise typer.Exit(1)
    if not groups:
        console.print("[yellow]No groups found.[/yellow]")
        return
    table = Table(title="Groups", box=box.SIMPLE_HEAVY)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Members", style="magenta")
    for g in groups:
        table.add_row(str(g.get("id")), g.get("name", ""), str(len(g.get("members", []))))
    console.print(table)


@app.command("former-groups")
def former_groups() -> None:
    try:
        client = build_client_from_env()
        groups = client.list_former_groups()
    except GroupMeAPIError as e:
        console.print(f"[red]Error listing former groups:[/red] {e}")
        raise typer.Exit(1)
    if not groups:
        console.print("[yellow]No former groups found.[/yellow]")
        return
    table = Table(title="Former Groups", box=box.SIMPLE_HEAVY)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    for g in groups:
        table.add_row(str(g.get("id")), g.get("name", ""))
    console.print(table)


@app.command()
def read(group_id: str, limit: int = typer.Option(20, "--limit", min=1, help="Number of recent messages (max 500)")) -> None:
    """Read last N messages from a group."""
    if limit > 500:
        limit = 500
    try:
        client = build_client_from_env()
        messages = client.get_group_messages_latest(group_id, limit=limit)
    except GroupMeAPIError as e:
        console.print(f"[red]Error fetching messages:[/red] {e}")
        raise typer.Exit(1)
    if not messages:
        console.print("[yellow]No messages found.[/yellow]")
        return
    # Messages are newest-first; display oldest-first for natural reading.
    for msg in reversed(messages):
        ts = _format_ts(msg.get("created_at"))
        name = msg.get("name") or msg.get("sender_id")
        text = msg.get("text") or ""
        attachments = msg.get("attachments") or []
        attach_note = f" [dim]{len(attachments)} attachment(s)[/dim]" if attachments else ""
        console.print(f"[cyan]{ts}[/cyan] [bold]{name}[/bold]: {text}{attach_note}")


@app.command("read-dm")
def read_dm(user_id: str, limit: int = typer.Option(20, "--limit", min=1, help="Number of recent messages (max 500)")) -> None:
    """Read last N direct messages with a user."""
    if limit > 500:
        limit = 500
    try:
        client = build_client_from_env()
        messages = client.get_direct_messages(user_id, limit=limit)
    except GroupMeAPIError as e:
        console.print(f"[red]Error fetching direct messages:[/red] {e}")
        raise typer.Exit(1)
    if not messages:
        console.print("[yellow]No messages found.[/yellow]")
        return
    for msg in reversed(messages):
        ts = _format_ts(msg.get("created_at"))
        name = (msg.get("name") or msg.get("sender_id") or "-")
        text = msg.get("text") or ""
        console.print(f"[cyan]{ts}[/cyan] [bold]{name}[/bold]: {text}")


@app.command()
def send(
    group_id: str,
    message: str = typer.Argument(..., help="Message text"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print payload without sending"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before sending"),
) -> None:
    """Send a message to a group."""
    if confirm and not dry_run:
        if not Confirm.ask(f"Send message to group {group_id}?"):
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()
    try:
        client = build_client_from_env()
        resp = client.send_group_message(group_id, message, dry_run=dry_run)
    except GroupMeAPIError as e:
        console.print(f"[red]Error sending message:[/red] {e}")
        raise typer.Exit(1)
    if dry_run:
        console.print(Panel.fit(str(resp["payload"]), title="Dry Run Payload", style="blue"))
    else:
        console.print("[green]Message sent.[/green]")


@app.command()
def dm(
    user_id: str,
    message: str = typer.Argument(..., help="Message text"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print payload without sending"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before sending"),
) -> None:
    """Send a direct message to a user."""
    if confirm and not dry_run:
        if not Confirm.ask(f"Send DM to user {user_id}?"):
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()
    try:
        client = build_client_from_env()
        resp = client.send_direct_message(user_id, message, dry_run=dry_run)
    except GroupMeAPIError as e:
        console.print(f"[red]Error sending DM:[/red] {e}")
        raise typer.Exit(1)
    if dry_run:
        console.print(Panel.fit(str(resp["payload"]), title="Dry Run Payload", style="blue"))
    else:
        console.print("[green]DM sent.[/green]")


@app.command("send-dm")
def send_dm(
    user_id: str,
    message: str = typer.Argument(..., help="Message text"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print payload without sending"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before sending"),
) -> None:
    """Alias for `dm` (send a direct message)."""
    dm.callback = None  # appease type checkers; we just delegate
    return dm(user_id=user_id, message=message, dry_run=dry_run, confirm=confirm)


@app.command("list-dms")
def list_dms() -> None:
    """List DM chats (other user + last message snippet)."""
    try:
        client = build_client_from_env()
        chats = client.list_chats()
    except GroupMeAPIError as e:
        console.print(f"[red]Error listing chats:[/red] {e}")
        raise typer.Exit(1)
    if not chats:
        console.print("[yellow]No DM chats found.[/yellow]")
        return
    table = Table(title="DM Chats", box=box.SIMPLE_HEAVY)
    table.add_column("User ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Last Message", style="magenta")
    for chat in chats:
        other_user = chat.get("other_user", {})
        last_msg = chat.get("last_message", {})
        snippet = (last_msg.get("text") or "").replace("\n", " ")
        if len(snippet) > 60:
            snippet = snippet[:57] + "..."
        table.add_row(str(other_user.get("id")), other_user.get("name", ""), snippet)
    console.print(table)


@app.command()
def like(group_id: str, message_id: str) -> None:
    """Like a message in a group."""
    try:
        client = build_client_from_env()
        client.like_message(group_id, message_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error liking message:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Liked.[/green]")


@app.command()
def unlike(group_id: str, message_id: str) -> None:
    """Unlike a message in a group."""
    try:
        client = build_client_from_env()
        client.unlike_message(group_id, message_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error unliking message:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Unliked.[/green]")


@app.command()
def whoami() -> None:
    """Show current user info."""
    try:
        client = build_client_from_env()
        me = client.get_me()
    except GroupMeAPIError as e:
        console.print(f"[red]Error fetching user info:[/red] {e}")
        raise typer.Exit(1)
    table = Table(title="You", box=box.SIMPLE_HEAVY)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    for k in ["id", "name", "phone_number", "email", "image_url"]:
        v = me.get(k)
        table.add_row(k, str(v) if v is not None else "-")
    console.print(table)


# ----------------------------- Groups ---------------------------------------

@app.command("group")
def group_show(group_id: str) -> None:
    """Show details for a group."""
    try:
        client = build_client_from_env()
        g = client.get_group(group_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error fetching group:[/red] {e}")
        raise typer.Exit(1)
    table = Table(title=f"Group {g.get('name','')} ({g.get('id')})", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    for k in ["description", "share", "office_mode", "created_at"]:
        table.add_row(k, str(g.get(k)))
    console.print(table)


@app.command("group-create")
def group_create(name: str, description: Optional[str] = typer.Option(None), share: bool = typer.Option(False)) -> None:
    try:
        client = build_client_from_env()
        g = client.create_group(name, description=description, share=share)
    except GroupMeAPIError as e:
        console.print(f"[red]Error creating group:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Created group {g.get('id')}[/green]")


@app.command("group-update")
def group_update(
    group_id: str,
    name: Optional[str] = typer.Option(None),
    description: Optional[str] = typer.Option(None),
    share: Optional[bool] = typer.Option(None),
    office_mode: Optional[bool] = typer.Option(None),
    image_url: Optional[str] = typer.Option(None),
) -> None:
    try:
        client = build_client_from_env()
        g = client.update_group(group_id, name=name, description=description, share=share, office_mode=office_mode, image_url=image_url)
    except GroupMeAPIError as e:
        console.print(f"[red]Error updating group:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Updated group {g.get('id')}[/green]")


@app.command("group-leave")
def group_leave(group_id: str) -> None:
    try:
        client = build_client_from_env()
        client.leave_group(group_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error leaving group:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Left group.[/green]")


@app.command("group-destroy")
def group_destroy(group_id: str) -> None:
    try:
        client = build_client_from_env()
        client.destroy_group(group_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error destroying group:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Destroyed group.[/green]")


@app.command("group-join")
def group_join(group_id: str) -> None:
    try:
        client = build_client_from_env()
        client.rejoin_group(group_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error joining group:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Joined group.[/green]")


@app.command("group-add-members")
def group_add_members(
    group_id: str,
    member: list[str] = typer.Option([], "--member", help="Repeatable key=val pairs, e.g., nickname=Sam,user_id=123"),
) -> None:
    """Invite/add members to a group.

    Each --member is a comma-separated list of key=value for fields: nickname, user_id, phone_number, email.
    Example: --member nickname=Alex,user_id=123 --member nickname=Bea,phone_number=+15551234567
    """
    members = []
    for m in member:
        entry: dict[str, str] = {}
        for p in [p.strip() for p in m.split(",") if p.strip()]:
            if "=" in p:
                k, v = p.split("=", 1)
                entry[k.strip()] = v.strip()
        if entry:
            members.append(entry)
    if not members:
        console.print("[red]Provide at least one --member entry.[/red]")
        raise typer.Exit(2)
    try:
        client = build_client_from_env()
        resp = client.add_members(group_id, members)
    except GroupMeAPIError as e:
        console.print(f"[red]Error adding members:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Add requested.[/green] results_id: {resp.get('results_id')}")


@app.command("group-members-results")
def group_members_results(group_id: str, results_id: str) -> None:
    try:
        client = build_client_from_env()
        resp = client.get_members_results(group_id, results_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error fetching add results:[/red] {e}")
        raise typer.Exit(1)
    console.print(resp)


@app.command("group-remove-member")
def group_remove_member(group_id: str, membership_id: str) -> None:
    try:
        client = build_client_from_env()
        client.remove_member(group_id, membership_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error removing member:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Member removed.[/green]")


# ----------------------------- Bots -----------------------------------------

@app.command("bots")
def bots_list() -> None:
    try:
        client = build_client_from_env()
        bots = client.list_bots()
    except GroupMeAPIError as e:
        console.print(f"[red]Error listing bots:[/red] {e}")
        raise typer.Exit(1)
    table = Table(title="Bots", box=box.SIMPLE_HEAVY)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Group")
    for b in bots:
        table.add_row(b.get("bot_id") or b.get("id") or "-", b.get("name", ""), str(b.get("group_id", "")))
    console.print(table)


@app.command("bot-create")
def bot_create(name: str, group_id: str, avatar_url: Optional[str] = typer.Option(None), callback_url: Optional[str] = typer.Option(None)) -> None:
    try:
        client = build_client_from_env()
        b = client.create_bot(name=name, group_id=group_id, avatar_url=avatar_url, callback_url=callback_url)
    except GroupMeAPIError as e:
        console.print(f"[red]Error creating bot:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Created bot {b.get('bot',{}).get('bot_id') or b.get('bot_id')}[/green]")


@app.command("bot-post")
def bot_post(bot_id: str, text: str, picture_url: Optional[str] = typer.Option(None)) -> None:
    try:
        client = build_client_from_env()
        client.post_bot_message(bot_id, text, picture_url=picture_url)
    except GroupMeAPIError as e:
        console.print(f"[red]Error posting via bot:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Bot message posted.[/green]")


@app.command("bot-destroy")
def bot_destroy(bot_id: str) -> None:
    try:
        client = build_client_from_env()
        client.destroy_bot(bot_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error destroying bot:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Bot destroyed.[/green]")


# ----------------------------- Search, Pins, Announce ----------------------

@app.command("search")
def search(group_id: str, query: str) -> None:
    try:
        client = build_client_from_env()
        resp = client.search_group_messages(group_id, query)
    except GroupMeAPIError as e:
        console.print(f"[red]Error searching messages:[/red] {e}")
        raise typer.Exit(1)
    messages = resp.get("messages", []) if isinstance(resp, dict) else []
    if not messages:
        console.print("[yellow]No results.[/yellow]")
        return
    for msg in messages:
        ts = _format_ts(msg.get("created_at"))
        name = msg.get("name") or msg.get("sender_id")
        text = msg.get("text") or ""
        console.print(f"[cyan]{ts}[/cyan] [bold]{name}[/bold]: {text}")


@app.command("pin")
def pin(group_id: str, message_id: str) -> None:
    try:
        client = build_client_from_env()
        client.pin_message(group_id, message_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error pinning message:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Pinned.[/green]")


@app.command("unpin")
def unpin(group_id: str, message_id: str) -> None:
    try:
        client = build_client_from_env()
        client.unpin_message(group_id, message_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error unpinning message:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Unpinned.[/green]")


@app.command("announce")
def announce(group_id: str, text: str) -> None:
    try:
        client = build_client_from_env()
        body = {"announcement": {"text": text}}
        client.create_announcement(group_id, body)
    except GroupMeAPIError as e:
        console.print(f"[red]Error creating announcement:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Announcement created.[/green]")


# ----------------------------- Power: Watch ---------------------------------

@app.command("watch")
def watch(group_id: Optional[str] = typer.Option(None, "--group-id")) -> None:
    """Live tail updates via WebSocket gateway."""
    token = os.getenv("GROUPME_TOKEN")
    if not token:
        console.print("[red]Missing GROUPME_TOKEN.[/red]")
        raise typer.Exit(2)
    try:
        client = build_client_from_env()
        me = client.get_me()
    except GroupMeAPIError as e:
        console.print(f"[red]Auth error:[/red] {e}")
        raise typer.Exit(1)
    user_id = str(me.get("id"))
    channels = [f"/user/{user_id}"]
    async def _run():
        async for data in watch_group(user_id, token, channels):
            subj = data.get("subject") or {}
            text = subj.get("text") or subj.get("name") or str(data)[:200]
            console.print(f"[dim]event[/dim] {data.get('type','?')}: {text}")
    asyncio.run(_run())


# ----------------------------- Power: Bulk likes ----------------------------

@app.command("bulk-like")
def bulk_like(conversation_id: str, message_ids: List[str] = typer.Argument(...)) -> None:
    try:
        client = build_client_from_env()
        ids = [{"conversation_id": conversation_id, "message_id": mid} for mid in message_ids]
        resp = client.bulk_like(ids)
    except GroupMeAPIError as e:
        console.print(f"[red]Error bulk-like:[/red] {e}")
        raise typer.Exit(1)
    console.print(str(resp))


@app.command("bulk-unlike")
def bulk_unlike(conversation_id: str, message_ids: List[str] = typer.Argument(...)) -> None:
    try:
        client = build_client_from_env()
        ids = [{"conversation_id": conversation_id, "message_id": mid} for mid in message_ids]
        resp = client.bulk_unlike(ids)
    except GroupMeAPIError as e:
        console.print(f"[red]Error bulk-unlike:[/red] {e}")
        raise typer.Exit(1)
    console.print(str(resp))


# ----------------------------- Power: Export --------------------------------

@app.command("export")
def export(group_id: str, out: str = typer.Option("group_export.json"), csv_out: Optional[str] = typer.Option(None)) -> None:
    try:
        client = build_client_from_env()
    except GroupMeAPIError as e:
        console.print(f"[red]Auth error:[/red] {e}")
        raise typer.Exit(1)
    msgs = list(export_group_messages(client, group_id))
    Path(out).write_text(json.dumps(msgs, indent=2))
    console.print(f"[green]Wrote {len(msgs)} messages to {out}[/green]")
    if csv_out:
        with open(csv_out, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "created_at", "name", "text", "likes"])
            for m in msgs:
                writer.writerow([m.get("id"), m.get("created_at"), m.get("name"), (m.get("text") or "").replace("\n"," "), len(m.get("favorited_by", []))])
    console.print(f"[green]Also wrote CSV to {csv_out}[/green]")


# ----------------------------- Power: Search DM -----------------------------

@app.command("search-dm")
def search_dm(query: str, user_id: Optional[str] = typer.Option(None, "--user-id")) -> None:
    try:
        client = build_client_from_env()
        resp = client.search_direct_messages(query, other_user_id=user_id)
    except GroupMeAPIError as e:
        console.print(f"[red]Error searching DMs:[/red] {e}")
        raise typer.Exit(1)
    dms = resp.get("direct_messages", []) if isinstance(resp, dict) else []
    if not dms:
        console.print("[yellow]No results.[/yellow]")
        return
    for msg in dms:
        ts = _format_ts(msg.get("created_at"))
        name = msg.get("name") or msg.get("sender_id")
        text = msg.get("text") or ""
        console.print(f"[cyan]{ts}[/cyan] [bold]{name}[/bold]: {text}")


# ----------------------------- Power: Stats ---------------------------------

@app.command("stats")
def stats(group_id: str) -> None:
    try:
        client = build_client_from_env()
        msgs = list(export_group_messages(client, group_id))
        s = stats_from_messages(msgs)
    except GroupMeAPIError as e:
        console.print(f"[red]Error fetching stats:[/red] {e}")
        raise typer.Exit(1)
    console.print("Top posters:")
    for name, cnt in s["top_posters"]:
        console.print(f"  {name}: {cnt}")
    console.print("Most liked:")
    for likes, m in s["most_liked"]:
        console.print(f"  {likes}❤  {m.get('name')}: {(m.get('text') or '')[:60]}")
    console.print("Busiest hours (UTC hour -> count):")
    console.print(", ".join(f"{h}: {c}" for h, c in s["hour_hist"]))


# ----------------------------- GUI -----------------------------------------

@app.command("gui")
def gui(host: str = typer.Option("0.0.0.0"), port: int = typer.Option(8000)) -> None:
    """Start the web GUI (FastAPI). Use Codespaces Port Forwarding."""
    uvicorn.run("webapp:app", host=host, port=port, reload=False, access_log=False)


# ----------------------------- Images --------------------------------------

@app.command("upload-image")
def upload_image(file_path: str) -> None:
    try:
        client = build_client_from_env()
        url = client.upload_image(file_path)
    except GroupMeAPIError as e:
        console.print(f"[red]Error uploading image:[/red] {e}")
        raise typer.Exit(1)
    console.print(url)


@app.command("send-image")
def send_image(group_id: str, file_path: str, message: Optional[str] = typer.Option("")) -> None:
    try:
        client = build_client_from_env()
        picture_url = client.upload_image(file_path)
        attachments = [{"type": "image", "url": picture_url}]
        client.send_group_message(group_id, message or "", attachments=attachments)
    except GroupMeAPIError as e:
        console.print(f"[red]Error sending image:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Image sent.[/green]")


def main():  # pragma: no cover - entrypoint
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[red]Interrupted[/red]")
        sys.exit(130)


if __name__ == "__main__":
    main()
