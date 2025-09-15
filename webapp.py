from __future__ import annotations

import os
from typing import Any, Dict

import os
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from groupme_api import build_client_from_env, GroupMeAPIError

app = FastAPI(title="GroupMe GUI")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape())


def render(template: str, **ctx: Dict[str, Any]) -> HTMLResponse:
    return HTMLResponse(env.get_template(template).render(**ctx))


@app.get("/")
def home() -> HTMLResponse:
    try:
        client = build_client_from_env()
        groups = client.list_all_groups()
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("index.html", groups=groups)


@app.get("/group/{group_id}")
def group_view(group_id: str, q: str | None = None) -> HTMLResponse:
    try:
        client = build_client_from_env()
        group = client.get_group(group_id)
        if q:
            resp = client.search_group_messages(group_id, q)
            messages = resp.get("messages", []) if isinstance(resp, dict) else []
        else:
            resp = client.get_group_messages(group_id, limit=50)
            messages = resp.get("messages", []) if isinstance(resp, dict) else []
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("group.html", group=group, messages=messages, q=q)


@app.post("/group/{group_id}/send")
def group_send(group_id: str, text: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        if text:
            client.send_group_message(group_id, text)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/groups/create")
def groups_create(name: str = Form(...), description: str = Form("") ) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.create_group(name, description=description or None)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url="/", status_code=302)


@app.post("/group/{group_id}/pin")
def group_pin(group_id: str, message_id: str = Form(...)) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.pin_message(group_id, message_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/unpin")
def group_unpin(group_id: str, message_id: str = Form(...)) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.unpin_message(group_id, message_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/like")
def group_like(group_id: str, message_id: str = Form(...)) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.like_message(group_id, message_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/unlike")
def group_unlike(group_id: str, message_id: str = Form(...)) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.unlike_message(group_id, message_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/announce")
def group_announce(group_id: str, text: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        if text:
            client.create_announcement(group_id, {"announcement": {"text": text}})
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/add-member")
def group_add_member(group_id: str, nickname: str = Form(""), user_id: str = Form(""), phone_number: str = Form(""), email: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        m = {k: v for k, v in {"nickname": nickname, "user_id": user_id, "phone_number": phone_number, "email": email}.items() if v}
        if m:
            client.add_members(group_id, [m])
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/export")
def group_export(group_id: str, filename: str = Form("group_export.json")) -> RedirectResponse:
    # For Codespaces simplicity, we don't stream download; we write to workspace and link from UI in future.
    try:
        client = build_client_from_env()
        from utils import export_group_messages
        import json, os
        msgs = list(export_group_messages(client, group_id))
        with open(os.path.join(os.getcwd(), filename), "w") as f:
            json.dump(msgs, f, indent=2)
    except Exception:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.get("/dms")
def dms_index() -> HTMLResponse:
    try:
        client = build_client_from_env()
        chats = client.list_chats()
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("dms.html", chats=chats)


@app.get("/watch")
def watch_page() -> HTMLResponse:
    return render("watch.html")


# ------------------ DMs ------------------

@app.get("/dm/{user_id}")
def dm_view(user_id: str) -> HTMLResponse:
    try:
        client = build_client_from_env()
        messages = client.get_direct_messages(user_id, limit=50)
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    other_name = None
    if messages:
        # Try to locate other party's name
        for m in messages:
            if str(m.get("sender_id")) != user_id and m.get("name"):
                other_name = m.get("name")
                break
    return render("dm.html", user_id=user_id, messages=list(reversed(messages)), other_name=other_name)


@app.post("/dm/{user_id}/send")
def dm_send(user_id: str, text: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        if text:
            client.send_direct_message(user_id, text)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/dm/{user_id}", status_code=302)


@app.get("/dms/search")
def dms_search(q: str = "", user_id: str | None = None) -> HTMLResponse:
    if not q:
        return render("dms.html", chats=[], q=q, results=[])
    try:
        client = build_client_from_env()
        resp = client.search_direct_messages(q, other_user_id=user_id or None)
        results = resp.get("direct_messages", []) if isinstance(resp, dict) else []
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("dms.html", chats=[], q=q, results=results, user_id=user_id)


# ------------------ Bots -----------------

@app.get("/bots")
def bots_index() -> HTMLResponse:
    try:
        client = build_client_from_env()
        bots = client.list_bots()
        groups = client.list_all_groups()
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("bots.html", bots=bots, groups=groups)


@app.post("/bots/create")
def bots_create(name: str = Form(...), group_id: str = Form(...), avatar_url: str = Form(""), callback_url: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.create_bot(name=name, group_id=group_id, avatar_url=avatar_url or None, callback_url=callback_url or None)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url="/bots", status_code=302)


@app.post("/bots/{bot_id}/post")
def bots_post(bot_id: str, text: str = Form(""), picture_url: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        if text or picture_url:
            client.post_bot_message(bot_id, text or "", picture_url=picture_url or None)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url="/bots", status_code=302)


@app.post("/bots/{bot_id}/destroy")
def bots_destroy(bot_id: str) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.destroy_bot(bot_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url="/bots", status_code=302)


# ------------- Group admin & extras -------------

@app.post("/group/{group_id}/update")
def group_update(group_id: str, name: str = Form(""), description: str = Form(""), share: str = Form(""), office_mode: str = Form(""), image_url: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        kwargs: Dict[str, Any] = {}
        if name:
            kwargs["name"] = name
        if description:
            kwargs["description"] = description
        if share:
            kwargs["share"] = share.lower() in {"1", "true", "yes", "on"}
        if office_mode:
            kwargs["office_mode"] = office_mode.lower() in {"1", "true", "yes", "on"}
        if image_url:
            kwargs["image_url"] = image_url
        if kwargs:
            client.update_group(group_id, **kwargs)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/leave")
def group_leave(group_id: str) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.leave_group(group_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url="/", status_code=302)


@app.post("/group/{group_id}/destroy")
def group_destroy(group_id: str) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.destroy_group(group_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url="/", status_code=302)


@app.post("/group/{group_id}/join")
def group_join(group_id: str) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.rejoin_group(group_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.post("/group/{group_id}/remove-member")
def group_remove_member(group_id: str, membership_id: str = Form(...)) -> RedirectResponse:
    try:
        client = build_client_from_env()
        client.remove_member(group_id, membership_id)
    except GroupMeAPIError:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.get("/group/{group_id}/members-results")
def group_members_results(group_id: str, results_id: str) -> HTMLResponse:
    try:
        client = build_client_from_env()
        resp = client.get_members_results(group_id, results_id)
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("error.html", message=str(resp))


@app.post("/group/{group_id}/send-image")
def group_send_image(group_id: str, file: UploadFile = File(...), message: str = Form("")) -> RedirectResponse:
    try:
        client = build_client_from_env()
        # Save upload to a temp file path
        data = file.file.read()
        tmp_path = os.path.join(os.getcwd(), f"_upload_{group_id}_{file.filename}")
        with open(tmp_path, "wb") as f:
            f.write(data)
        picture_url = client.upload_image(tmp_path)
        os.remove(tmp_path)
        attachments = [{"type": "image", "url": picture_url}]
        client.send_group_message(group_id, message or "", attachments=attachments)
    except Exception:
        pass
    return RedirectResponse(url=f"/group/{group_id}", status_code=302)


@app.get("/group/{group_id}/stats")
def group_stats(group_id: str) -> HTMLResponse:
    try:
        client = build_client_from_env()
        from utils import export_group_messages, stats_from_messages
        msgs = list(export_group_messages(client, group_id))
        stats = stats_from_messages(msgs)
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("stats.html", group_id=group_id, stats=stats)


# ------------- Bulk like/unlike -------------

@app.get("/bulk")
def bulk_page() -> HTMLResponse:
    return render("bulk.html")


@app.post("/bulk/like")
def bulk_like(conversation_id: str = Form(...), message_ids: str = Form(...)) -> HTMLResponse:
    try:
        client = build_client_from_env()
        ids = [m.strip() for m in message_ids.replace("\r", "\n").replace(",", "\n").split("\n") if m.strip()]
        payload = [{"conversation_id": conversation_id, "message_id": mid} for mid in ids]
        result = client.bulk_like(payload)
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("bulk.html", result=result)


@app.post("/bulk/unlike")
def bulk_unlike(conversation_id: str = Form(...), message_ids: str = Form(...)) -> HTMLResponse:
    try:
        client = build_client_from_env()
        ids = [m.strip() for m in message_ids.replace("\r", "\n").replace(",", "\n").split("\n") if m.strip()]
        payload = [{"conversation_id": conversation_id, "message_id": mid} for mid in ids]
        result = client.bulk_unlike(payload)
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("bulk.html", result=result)


# ------------- Whoami & Former groups -------------

@app.get("/me")
def me() -> HTMLResponse:
    try:
        client = build_client_from_env()
        me = client.get_me()
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("me.html", me=me)


@app.get("/former")
def former_groups() -> HTMLResponse:
    try:
        client = build_client_from_env()
        groups = client.list_former_groups()
    except GroupMeAPIError as e:
        return render("error.html", message=str(e))
    return render("former.html", groups=groups)


# ------------- Watch SSE -------------

@app.get("/watch/stream")
async def watch_stream() -> StreamingResponse:
    async def event_gen():
        try:
            client = build_client_from_env()
            me = client.get_me()
            # Accept multiple possible shapes from client.get_me()
            user_id = None
            if isinstance(me, dict):
                if "id" in me:
                    user_id = str(me["id"])
                elif isinstance(me.get("response"), dict) and "id" in me["response"]:
                    user_id = str(me["response"]["id"])
            elif isinstance(me, list) and me and isinstance(me[0], dict) and "id" in me[0]:
                user_id = str(me[0]["id"])
            if not user_id:
                yield "data: {\"error\": \"Unexpected /me response shape\"}\n\n"
                return
            token = os.getenv("GROUPME_TOKEN")
            if not token:
                yield "data: {\"error\": \"Missing token\"}\n\n"
                return
            from utils import watch_group
            async for data in watch_group(user_id, token, [f"/user/{user_id}"]):
                import json as _json
                yield f"data: {_json.dumps(data)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream")
