# Python Virtual Environment Setup Guide

Follow these steps to set up a clean, isolated development environment for your project.

---

### Step 1: Install pip/pip3 Globally
Ensure that the Python package manager is installed on your system.
* **Windows/macOS/Linux:** 
```fish
  python -m ensurepip --upgrade
```
### Step 2: Install virtualenv using pip/pip3
Install the virtualenv tool globally using pip.
* **Windows/macOS/Linux:** 
```fish
 pip install virtualenv
```

### Step 3: Create a Project Folder
Create a directory for your new project.
* **Windows/macOS/Linux:** 
```fish
 mkdir my-python-project
```

### Step 4: Navigate to the Project Folder
Open your terminal or command prompt and navigate to the project directory.
* **Windows/macOS/Linux:** 
```fish
cd my-python-project
```

### Step 5: Create a Virtual Environment
Create a virtual environment using Python's built-in venv module.
* **Windows/macOS/Linux:** 
```fish
python -m venv <env-name>
```

### Step 6: Activate the Virtual Environment
Activate the virtual environment for your operating system.
* **Windows:** 
```fish
<env-name>\Scripts\activate
```
* **macOS/Linux:** 
```fish
source <env-name>/bin/activate
```

### Step 7: Install Required Packages
Install dependencies from your requirements.txt file.
* **Windows/macOS/Linux:** 
```fish
pip install -r requirements.txt
```

### Step 8: Deactivate the Virtual Environment
When finished, deactivate the virtual environment.
* **Windows/macOS/Linux:** 
```fish
deactivate
```