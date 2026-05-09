# Dripcheck Python API 🚀

Welcome to the **Dripcheck Python API**! This project is a robust, scalable backend built with **FastAPI** to manage user wardrobes, profiles, analytics, and wear logs. This version is a Python-based implementation of the original Dripcheck logic, optimized for performance and maintainability.

---

## 📑 Table of Contents
1. [Introduction](#introduction)
2. [Tech Stack](#tech-stack)
3. [Project Architecture](#project-architecture)
4. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Installation](#installation)
5. [Running the Application](#running-the-application)
6. [API Endpoints](#api-endpoints)
7. [Folder Structure](#folder-structure)
8. [Git Best Practices for Junior Developers](#git-best-practices)
9. [Contributing](#contributing)

---

## 📖 Introduction <a name="introduction"></a>
Dripcheck is an intelligent wardrobe management system. This Python backend handles the core business logic, including:
- **Wardrobe Management**: CRUD (Create, Read, Update, Delete) operations for clothing items.
- **User Profiles**: Managing user settings and preferences.
- **Wear Logs**: Tracking what you wear and when.
- **Analytics**: Providing insights into wardrobe usage.

---

## 🛠 Tech Stack <a name="tech-stack"></a>
- **Language**: Python 3.10+
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (High-performance web framework)
- **Data Validation**: [Pydantic](https://docs.pydantic.dev/) (Data parsing and validation)
- **Server**: [Uvicorn](https://www.uvicorn.org/) (ASGI server implementation)

---

## 🏗 Project Architecture <a name="project-architecture"></a>
The project consists of two main microservices (FastAPI applications):
1. **Core API (`main.py`)**: Handles wardrobe management, user profiles, and analytics. Runs on port `8000`.
2. **Bundle Generation API (`bundlegeneration.py`)**: Specialized service for generating outfit bundles and marketplace suggestions. Runs on port `8001`.

---

## 🚀 Getting Started <a name="getting-started"></a>

### 1. Prerequisites
Make sure you have the following installed on your machine:
- **Python 3.10 or higher**
- **pip** (Python package installer)
- **Git**

### 2. Installation
Follow these steps to set up the project locally:

**Step 1: Clone the repository**
```bash
git clone <your-repository-url>
cd dripcheck-with-python/dripcheck-api
```

**Step 2: Create a Virtual Environment**
It is highly recommended to use a virtual environment to avoid dependency conflicts.
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

**Step 3: Install Dependencies**
```bash
pip install -r requirements.txt
```

---

## 🏃 Running the Application <a name="running-the-application"></a>

Since there are two services, you need to run them separately (in different terminal windows):

### Start the Core API
```bash
python main.py
```
*Port: 8000 | Docs: [http://localhost:8000/docs](http://localhost:8000/docs)*

### Start the Bundle Generation API
```bash
python bundlegeneration.py
```
*Port: 8001 | Docs: [http://localhost:8001/docs](http://localhost:8001/docs)*

---

## 🛣 API Endpoints <a name="api-endpoints"></a>

### Core API (Port 8000)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/wardrobe/{user_id}` | Fetch all items in a user's wardrobe |
| `POST` | `/api/wardrobe/{user_id}` | Add a new item to the wardrobe |
| `PUT` | `/api/wardrobe/{user_id}/{item_id}` | Update a specific wardrobe item |
| `DELETE` | `/api/wardrobe/{user_id}/{item_id}` | Remove an item from the wardrobe |
| `GET` | `/api/users/{user_id}` | Retrieve user profile details |
| `PUT` | `/api/users/{user_id}` | Update user profile information |

### Bundle Generation API (Port 8001)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/bundles/{user_id}` | Get personalized outfit bundles |
| `POST` | `/api/bundles/{user_id}/save` | Save a specific bundle for the user |
| `GET` | `/api/marketplace` | Get curated marketplace bundles |

---

## 📂 Folder Structure <a name="folder-structure"></a>
```text
dripcheck-api/
├── main.py              # Entry point of the FastAPI application
├── requirements.txt      # List of dependencies
├── models/
│   └── types.py         # Pydantic models for data validation
├── services/
│   └── data_service.py   # Business logic and data handling
├── engine/              # Core logic for bundle generation
├── data/                # Static or persistent data storage
└── documents/           # Project documentation
```

---

## 🛠 Git Best Practices (For Junior Developers) <a name="git-best-practices"></a>
If you are new to Git, follow these rules to maintain a clean codebase:

1. **Pull Before You Push**: Always run `git pull origin main` before starting work to ensure you have the latest changes.
2. **Use Descriptive Commit Messages**: 
   - Good: `feat: add delete endpoint for wardrobe items`
   - Bad: `fixed stuff`
3. **Branching**: Never work directly on the `main` branch. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Small Commits**: Make small, logical commits rather than one massive commit at the end of the day.

---

## 🤝 Contributing
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat: Add some AmazingFeature'`)
4. Push to the Branch (`git pull origin feature/AmazingFeature`)
5. Open a Pull Request

---

Developed with ❤️ by the Dripcheck Team.
