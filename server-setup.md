# Server Setup Guide

Follow these steps to set up a clean, isolated development/production server.

---

### Step 1: Install Required Packages
Install dependencies from your requirements.txt file.
* **Windows/macOS/Linux:** 
```fish
pip install -r requirements.txt
```

### Step 2: Running the Server
Ensure the virtual enviroment & uvicorn are installed.
* **Windows/macOS/Linux:** 
```fish
 uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
### Step 3: Stopping the Server
When finished, stop the server by terminating the process in your terminal or command prompt.
* **Windows/macOS/Linux:**
```fish
 Ctrl + C
```