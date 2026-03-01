import time
from pymongo import MongoClient
import firebase_admin
from firebase_admin import credentials, messaging
from datetime import datetime, UTC



# Firebase init
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)

# MongoDB
client = MongoClient("mongodb://localhost:27017")
db = client.edu_users
users_col = db.users_noti_col
schedule_col = db.scheduled_notifications


def send_push_to_all_users(title, body):
    tokens = []

    for user in users_col.find():
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



def send_push_to_user(reg_no, title, body):
    user = users_col.find_one({"reg_no": reg_no})

    if not user or not user.get("fcm_token"):
        print(f"No FCM token for {reg_no}")
        return

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=user["fcm_token"],
    )

    messaging.send(message)
    print(f"Notification sent to {reg_no}")


def scheduler_loop():
    print("Scheduler started...")
    while True:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        jobs = schedule_col.find({
            "send_at": {"$lte": now},
            "sent": False
        })

        for job in jobs:
            if job["reg_no"] == "all":
                send_push_to_all_users(job["title"],job["body"])
                schedule_col.update_many(
                    {"_id": job["_id"]},
                    {"$set": {"sent": True}}
                )
            else:
                send_push_to_user(
                    job["reg_no"],
                    job["title"],
                    job["body"]
                )
                schedule_col.update_one(
                    {"_id": job["_id"]},
                    {"$set": {"sent": True}}
                )

        time.sleep(30)  # check every 30 sec


if __name__ == "__main__":
    scheduler_loop()
