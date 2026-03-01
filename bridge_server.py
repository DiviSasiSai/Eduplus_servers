from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime
import uuid
import requests
import asyncio
import firebase_admin
from firebase_admin import credentials, messaging


cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# MongoDB
client = MongoClient("mongodb://localhost:27017")
db = client.edu_users
users_col = db.users
users_noti_col = db.users_noti_col

# Active WebSocket connections
active_connections = {}


FASTAPI_TEXT_URL = "http://127.0.0.1:8000/whatsapp-message"
FASTAPI_IMAGE_URL = "http://127.0.0.1:8000/image-message"
FASTAPI_USER_URL = "http://127.0.0.1:8000/user-message"

TELEGRAM_TOKEN = "telegram bot token"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_push_to_all_users(title, body):
    tokens = []

    for user in users_noti_col.find():
        if user.get("fcm_token"):
            tokens.append(user["fcm_token"])

    if not tokens:
        print("status: no tokens")
        return

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        tokens=tokens,
    )

    response = messaging.send_each_for_multicast(message)

    print(f"success:{response.success_count},failed: {response.failure_count}")


# ---------------------------
# LOGIN
# ---------------------------
@app.post("/login")
def login(reg_no: str = Form(...), password: str = Form(...)):
    user = users_col.find_one({"reg_no": reg_no.lower().strip(), "password": password})
    if not user:
        return {"status": "error", "message": "Invalid credentials"}

    device_id = user.get("device_id")
    if not device_id:
        device_id = str(uuid.uuid4())
        users_col.update_one(
            {"reg_no": reg_no.lower()},
            {"$set": {"device_id": device_id}}
        )

    return {
        "status": "success",
        "reg_no": reg_no,
        "device_id": device_id
    }

# ---------------------------
# Telegram Webhook
# ---------------------------

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    sender = msg["from"].get("first_name", "")
    group = msg["chat"].get("title", "TelegramGroup")

    now = datetime.now()

    base_payload = {
        "chat_id": str(chat_id),
        "sender": sender,
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "group": group
    }

    # ---------------------------
    # TEXT / NON-IMAGE MESSAGES
    # ---------------------------
    if "text" in msg:
        payload = {**base_payload, "message": msg["text"]}
        resp = requests.post(FASTAPI_TEXT_URL, json=payload)
        print("suc1")
        message = resp.json()['message']
        if message == "@":
            return {"status": "sent"}
        send_push_to_all_users("AI",message)

        tasks = []

        for user in users_col.find():
            ws = active_connections.get(user['device_id'])
            if ws:
                tasks.append(
                    ws.send_json({
                        "from": "ai",
                        "message": message
                    })
                )

        if tasks:
            await asyncio.gather(*tasks)
        print("suc2")
        return {"status": "sent"}


    # ---------------------------
    # IMAGE MESSAGES
    # ---------------------------
    if "photo" in msg:
        # Get highest resolution image
        photo = msg["photo"][-1]
        file_id = photo["file_id"]

        # Step 1: Get file path
        file_resp = requests.get(
            f"{TELEGRAM_API}/getFile",
            params={"file_id": file_id}
        ).json()

        file_path = file_resp["result"]["file_path"]

        # Step 2: Download image
        image_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        image_bytes = requests.get(image_url).content

        # Step 3: Send as multipart/form-data
        files = {
            "image": ("telegram_image.jpg", image_bytes, "image/jpeg")
        }

        resp = requests.post(
            FASTAPI_IMAGE_URL,
            data=base_payload,
            files=files
        )
        print("suc1")
        message = resp.json()['message']
        send_push_to_all_users("AI",message)
        tasks = []

        for user in users_col.find():
            ws = active_connections.get(user['device_id'])
            if ws:
                tasks.append(
                    ws.send_json({
                        "from": "ai",
                        "message": message
                    })
                )

        if tasks:
            await asyncio.gather(*tasks)
        print("suc2")
        return {"status": "sent"}
    return {"status": "sent"}


# ---------------------------
# USER MESSAGE
# ---------------------------
@app.post("/user-message")
async def user_message(
    device_id: str = Form(...),
    reg_no: str = Form(...),
    message: str = Form(...)
):
    payload={"reg_no":reg_no.lower(),"message":message}
    print(payload)
    resp = requests.post(FASTAPI_USER_URL, json=payload)
    message = resp.json()['message']
    ai_reply = f"AI: {message}"

    # Push via WebSocket
    ws = active_connections.get(device_id)
    if ws:
        await ws.send_json({
            "from": "ai",
            "message": ai_reply
        })

    return {"status": "sent"}

@app.post("/save-fcm")
def save_fcm(reg_no: str = Form(...), device_id: str = Form(...), fcm_token: str = Form(...)):
    if users_noti_col.find_one({"reg_no":reg_no.lower()}) :
        users_noti_col.update_one({"reg_no":reg_no.lower()},{"$set":{"fcm_token": fcm_token}})
    else:
        users_noti_col.insert_one({"reg_no": reg_no.lower(),"fcm_token": fcm_token})
    return {"status": "ok"}

@app.post("/logout")
def logout(reg_no: str = Form(...)):
    users_noti_col.delete_one({"reg_no": reg_no.lower()})
    users_col.update_one({"reg_no":reg_no.lower()},{"$set":{"device_id":None}})
    return {"status": "logged_out"}



# ---------------------------
# WEBSOCKET
# ---------------------------
@app.websocket("/ws/{device_id}")
async def websocket_endpoint(ws: WebSocket, device_id: str):
    await ws.accept()
    active_connections[device_id] = ws

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        active_connections.pop(device_id, None)

