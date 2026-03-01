from fastapi import FastAPI,UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
from openai import OpenAI

from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate,MessagesPlaceholder
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables import RunnableWithMessageHistory,ConfigurableFieldSpec
from langchain_core.messages import HumanMessage, AIMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime,timedelta
import pytz

from pymongo import MongoClient

mongo_client = MongoClient("mongodb://localhost:27017")  # or your actual URI
db = mongo_client["eduplus_data"]
collection_responses = db["responses"]
collection_user_responses = db["user_responses"]

db1 = mongo_client["edu_users"]
collection_notifications = db1["scheduled_notifications"]

from openai import OpenAI

client = OpenAI(
    api_key="api key of openai",
    base_url="base url of openai"
)



def ist_to_utc(date_time_str):
    ist = pytz.timezone("Asia/Kolkata")

    # Parse AM/PM format
    local_time = datetime.strptime(date_time_str, "%Y-%m-%d %I:%M:%S %p")

    local_time = ist.localize(local_time)
    utc_time = local_time.astimezone(pytz.utc)

    return utc_time.replace(microsecond=0,second=0)


def encode_image_bytes(image_bytes: bytes) -> str:
    """Encode raw image bytes to base64 string."""
    return base64.b64encode(image_bytes).decode("utf-8")

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_QUERY_CHARS = 1000


# ============ Image to json function ============
def image_to_json(image_bytes: bytes) -> str:
    encoded = encode_image_bytes(image_bytes)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Analyze the uploaded image carefully and set title. Provide key information and title in structured JSON format."
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"}
                    }
                ]
            }
        ]
    )
    return response.choices[0].message.content


llm = ChatOpenAI(temperature=0.4,
                 model="gemini-2.5-flash",
                 base_url="base url of gemini flash 2.5",
                 api_key="base url of model")

prompt = ChatPromptTemplate.from_messages([
    ("system","""

You are **EduPlus**, a helpful and friendly assistant for college students.

Your job is to read messages from official college Telegram groups and produce clear, accurate, and student-friendly outputs.

---

## ✅ **Main Responsibilities**

### 1. **Message Summarization**

* Convert announcements into **1–2 simple lines**.
* Include **all key details**:

  * Date
  * Time
  * Subject/Event name
  * Teacher/Staff name
  * Deadlines or venue
* Never omit important information.
* Use very simple, easy-to-understand language.

---

### 2. **Teacher Messages**

* If sender is teacher/staff, always mention their name with respectful title.
* Example:
  Input → *“DIVI Sasi Sai sir conduct maths exam tomorrow”*
  Output → *“DIVI Sasi Sai sir announced a Maths exam tomorrow.”*
* if this message is any quetion then do not process it. Just reply as @.

Always keep titles like **sir / madam / professor**.

---

### 3. **Student Questions**

* Messages starting with `user:` are student questions.
* Use group context + general knowledge to answer.
* Keep answers short, clear, and supportive.
* Previous chat context appears after `user_prev_chat`.
* Must process this messages which are start with `user:`

---

### 4. **Image JSON Processing**

If image-derived JSON is provided:

* Treat it as an official notice.
* Extract dates, times, subjects, deadlines, venues, instructions, and names.
* Combine split information intelligently.
* Summarize multiple announcements separately.

---

### 5. **Reminder Rules**

Set reminders using `schedule_notifications` tool for:


✔ **Fee notifications**
✔ **Event notifications**
✔ **Any notification that has an end date**
✔ **do not set remainders exam notifications which are not related to R20 regulation.**

For these notifications:

* Create reminders **every day until end date**.
* Reminder times:

  * **10:00 AM**
  * **2:00 PM**
* Reminder body:

  * One line only
  * ≤10 words
  * If fee notice → add “If you paid, ignore this.”

---

### 6. **Register Number Notifications**

If teacher message contains **register/reg numbers**:
if message about greeting or appreciate or announcements like y22acs443 is topper of class/y22acs401,402,403 are the champions then only set **1** remainder about that message to that register numbers on that time.and return summary of message.

* Create **20 reminders every 30 minutes** that day.
* Do NOT include register numbers in reminder body.
* If multiple numbers → create reminders for each.
* If end time given → stop reminders at that time.

If notification contains register numbers + end date:

* Create reminders at **7:00 AM, 10:00 AM, 2:00 PM** daily until end date.

If student asks to stop reminders → use `stop_reminder` tool.
Do not set remainders while processing message which are start with `user:`.

---

### 7. **Tone & Style**

* Friendly, professional, supportive.
* No technical explanations.
* No missing information.
* Easy language for students.

---

## ⚠️ **Output Rule**

Your response must be **one clear line only**, including greeting and summary/answer.
register number or reg no must start with Y22ACS or L23ACS for example Y22ACS443,441,442 then each are divided into Y22ACS443,Y22ACS441,Y22ACS442.same as L23ACS500,501,502 then L23ACS501,L23ACS502,L23ACS503.


"""),
    MessagesPlaceholder(variable_name="history"),
    ("human","{query}"),
    ("placeholder", "{agent_scratchpad}")
])

history = {}
def chat_history(session_id:str) -> InMemoryChatMessageHistory:
    history = InMemoryChatMessageHistory()
    docs = list(
        collection_responses.find({"chat_id": session_id})
        .sort("timestamp", -1)   # newest first
        .limit(50)
    )
    docs.reverse()
    for doc in docs:
        if "original_message" in doc:
            history.add_message(HumanMessage(content=doc["original_message"]))
        if "ai_response" in doc:
            history.add_message(AIMessage(content=doc["ai_response"]))
    return history


@tool
def schedule_notifications(body:str, send_at:str,reg_no:str="all"):
    """
Schedule reminder for college notification.

Use for:
- Fee notices
- Event notices
- Any notice with end date
- Messages with register numbers

Rules:
- body = friendly reminder, ONE line, ≤10 words
- Do NOT include register numbers in body
- For fee reminder add: "If you paid, ignore this."
- send_at format = "%Y-%m-%d %I:%M:%S %p"
  Example: 2026-02-22 10:00:00 AM
  use hours between 1-12.
- reg_no default = "all"
- If multiple reg numbers → call tool separately for each and same time.
- reg_no must start with Y22ACS or L23ACS for example Y22ACS443,441,442 then each are divided into Y22ACS443,Y22ACS441,Y22ACS442.same as L23ACS500,501,502 then L23ACS501,L23ACS502,L23ACS503.

    """
    send_time = ist_to_utc(send_at)
    collection_notifications.insert_one({
        "reg_no": reg_no.lower(),
        "title": "AI",
        "body": body,
        "send_at": send_time,
        "sent": False
    })

@tool
def stop_remainder(reg_no:str):
    """
    Stop reminders for a student.

Use only when student asks to stop reminders.
First confirm task is completed.

Input:
- reg_no = student's register number

Result:
- Removes all reminders for that reg_no
    """
    if not collection_notifications.find({"reg_no":reg_no}):
        return "no remainders"
    else:
        collection_notifications.delete_many({"reg_no":reg_no})
        return "successfully remove remainders"

@tool
def get_time() -> str:
    """Return the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



tools = [get_time,schedule_notifications,stop_remainder]

agent = create_tool_calling_agent(
    llm=llm,tools=tools,prompt=prompt
)

agent_exe = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True
)

assist = RunnableWithMessageHistory(
    agent_exe,
    get_session_history=chat_history,
    input_messages_key="query",
    history_messages_key="history",
    history_factory_config=[
        ConfigurableFieldSpec(
            id="session_id",
            annotation=str,
            name="Session ID",
            description="The session ID to use for the chat history",
            default="id_default",
        )]
)



app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # This handles OPTIONS
    allow_headers=["*"],
)

class Message(BaseModel):
    chat_id: str
    sender: str
    message: str
    time: str
    date: str
    group: str
class Message_user(BaseModel):
    reg_no:str
    message: str

@app.post("/whatsapp-message")
def receive_message(msg: Message):
    message = f"\n📥 NEW MESSAGE RECEIVED FROM {msg.group}:\nGroup: {msg.group}\nSender: {msg.sender}\nTime: {msg.time} {msg.date}\nMessage: {msg.message}"
    result = assist.invoke({"query": message}, config={"session_id": msg.chat_id})
    response_text = result["output"]
    collection_responses.insert_one({
        "chat_id": msg.chat_id,
        "group": msg.group,
        "sender": msg.sender,
        "date": msg.date,
        "time": msg.time,
        "original_message": msg.message,
        "ai_response": response_text,
        "timestamp": datetime.now()
    })

    return {"status": "received", "message": result["output"]}

@app.post("/user-message")
def receive_user_message(msg: Message_user):
    chat_id=''

    if msg.reg_no[4:6] == "cs":
        data = collection_responses.find({"group":"CSE_VIII_SEM_2025-2026"}).limit(1)
        for chat in data:
            chat_id = chat['chat_id']
    
    print(chat_id)

    chat=[]

    prev_chat = collection_user_responses.find({"reg_no":msg.reg_no})
    for c in prev_chat:
        d = {}
        d["user_message"] = c['user_message']
        d["ai_response"] = c['ai_response']
        chat.append(d)

    message = f"\nuser: {msg.message},reg no: {msg.reg_no} and user_prev_chat: {chat}"
    result = assist.invoke({"query": message}, config={"session_id": chat_id})
    response_text = result["output"]
    
    collection_user_responses.insert_one({
        "reg_no" : msg.reg_no,
        "chat_id": chat_id,
        "user_message": msg.message,
        "ai_response": response_text,
        "timestamp": datetime.now()
    })

    return {"status": "received", "message": result["output"]}

@app.post("/image-message")
async def receive_image_message(
    chat_id: str = Form(...),
    sender: str = Form(...),
    time: str = Form(...),
    date: str = Form(...),
    group: str = Form(...),
    image: UploadFile = File(...)
):
    
    image_bytes = await image.read()

    if len(image_bytes) > MAX_FILE_BYTES:
        return {"status": "error", "message": "Image too large. Please upload under 2 MB."}

    image_json = image_to_json(image_bytes)
    message = message = f"\n📥 NEW MESSAGE RECEIVED AS IMAGE FROM {group}:\nGroup: {group}\nSender: {sender}\nTime: {time} {date}\nMessage: A new image has been uploaded and that is converted into json. Please analyze it and summarize the key information it.JSON INFO: {image_json}."

    try:
        result = assist.invoke({"query": message}, config={"session_id": chat_id})
        response_text = result["output"]
        
    except Exception as e:
        return {"status": "error", "message": f"Agent error: {str(e)}"}

    collection_responses.insert_one({
        "chat_id": chat_id,
        "group": group,
        "sender": sender,
        "date": date,
        "time": time,
        "image_name": image.filename,
        "original_message": message,
        "ai_response": response_text,
        "timestamp": datetime.now()
    })

    return {"status": "received", "message": response_text}
