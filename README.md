# Eduplus: Intelligent Telegram Assistant For Student Updates And Remainders 🧠📚💻
The Notification and Image Analysis Platform is a comprehensive system designed to handle various tasks, including user login, Telegram webhooks, image analysis, and push notifications. The platform consists of multiple servers, each responsible for a specific set of tasks, and utilizes a MongoDB database to store user information, scheduled notifications, and image analysis results. The core features of the platform include user login and authentication, Telegram webhook handling, image analysis using the OpenAI API, and push notification scheduling and sending.

## 🚀 Features
- User login and authentication using the `bridge_server.py` file
- Telegram webhook handling and processing using the `bridge_server.py` file
- Image analysis using the OpenAI API and the `agent_server.py` file
- Push notification scheduling and sending using the `notification_scheduler.py` file
- Integration with MongoDB database for storing user information, scheduled notifications, and image analysis results
- Utilization of Firebase Cloud Messaging (FCM) service for sending push notifications

## 🛠️ Tech Stack
- **Backend:** FastAPI, Python
- **Database:** MongoDB
- **AI Tools:** OpenAI API
- **Notification Service:** Firebase Cloud Messaging (FCM)
- **Libraries:** `pymongo`, `firebase_admin`, `requests`, `pydantic`, `openai`
- **Frameworks:** FastAPI, LangChain

## 📦 Installation
To install the required dependencies, run the following command:
```bash
pip install -r requirements.txt
```
### Prerequisites
- Python 3.12.6 or higher
- MongoDB database
- Firebase project with FCM service enabled
- OpenAI API key

### Setup Instructions
1. Clone the repository and navigate to the project directory.
2. Install the required dependencies using the command above.
3. Set up a MongoDB database and create the necessary collections (e.g., `users`, `users_noti_col`, `schedule_col`, `responses`, `user_responses`).
4. Create a Firebase project and enable the FCM service. Get fire base key.
5. Obtain an OpenAI API key and set it as an environment variable.

## 💻 Usage
To run the platform, start each server separately:
- `bridge_server.py`: handles user login, Telegram webhooks, and push notification scheduling
- `agent_server.py`: handles image analysis and interactions with the OpenAI API
- `notification_scheduler.py`: handles push notification sending

## 📂 Project Structure
```markdown
project/
├── bridge_server.py
├── agent_server.py
├── notification_scheduler.py
├── requirements.txt
├── README.md
```

## 📬 Contact
For any questions or concerns, please contact us at [divisasisai@gmail.com](mailto:divisasisai@gmail.com).

## 💖 Thanks Message
This project is made by the contributions of our B1 Batch members.
