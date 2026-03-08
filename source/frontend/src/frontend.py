import os
import requests
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Mars Dashboard")
templates = Jinja2Templates(directory="templates")

# URL to contact the Automation Engine (set in docker-compose)
LOGIC_API_URL = os.getenv("LOGIC_API_URL", "http://automation_engine:8000")

# Models to receive data from Javascript
class ActuatorCommand(BaseModel):
    actuator_name: str
    target_state: str

class RuleCommand(BaseModel):
    sensor_id: str
    metric: str
    operator: str
    threshold_value: float
    actuator_name: str
    target_state: str

@app.get("/")
def read_root(request: Request):
    """Renders the index.html page."""
    return templates.TemplateResponse("index.html", {"request": request})       

@app.get("/api/dashboard-data")
def get_dashboard_data():
    """Proxy point: contacts the Automation Engine to fetch updated data."""
    try:
        status_res = requests.get(f"{LOGIC_API_URL}/api/status", timeout=2)
        rules_res = requests.get(f"{LOGIC_API_URL}/api/rules", timeout=2)
        
        status_data = status_res.json() if status_res.status_code == 200 else {"sensors": {}, "actuators": {}}
        rules_data = rules_res.json() if rules_res.status_code == 200 else {"rules": []}
        
        return {
            "sensors": status_data.get("sensors", {}),
            "actuators": status_data.get("actuators", {}),
            "rules": rules_data.get("rules", [])
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Logic Engine: {e}", flush=True)
        return {"sensors": {}, "actuators": {}, "rules": [], "error": "Backend offline"}

@app.post("/api/toggle-actuator")
def toggle_actuator(cmd: ActuatorCommand):
    """Proxy request to switch the actuator."""
    try:
        res = requests.post(f"{LOGIC_API_URL}/api/actuators", json=cmd.dict(), timeout=2)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/add-rule")
def create_rule(cmd: RuleCommand):
    """Proxy request to add a rule."""
    try:
        res = requests.post(f"{LOGIC_API_URL}/api/rules", json=cmd.dict(), timeout=2)
        if res.status_code != 200:
            err_detail = res.json().get("detail", "Error from Logic API")
            raise HTTPException(status_code=res.status_code, detail=err_detail)
        return res.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/delete-rule/{rule_id}")
def delete_rule(rule_id: int):
    """Proxy request to delete a rule."""
    try:
        res = requests.delete(f"{LOGIC_API_URL}/api/rules/{rule_id}", timeout=2)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))
