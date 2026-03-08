import threading
import requests
import mysql.connector
from fastapi import FastAPI, HTTPException

# Import all our logic, models, etc.
from src.logic import (
    Rule, 
    ManualCommand, 
    get_db_connection, 
    latest_sensor_data, 
    latest_actuator_state, 
    load_actuators_state, 
    rabbitmq_worker,
    SIMULATOR_URL,
    init_db
)

app = FastAPI(title="Mars Automation Engine")

# Worker starts on API startup
@app.on_event("startup")
def startup_event():
    # Initialize the database table if it doesn't exist
    init_db()
    
    load_actuators_state()

    # Starts RabbitMQ's consumer on a separate thread in order not to block FastAPI
    thread = threading.Thread(target=rabbitmq_worker, daemon=True)
    thread.start()

# ENDPOINT API (for the frontend)
@app.get("/api/rules")
def get_rules():
    """Returns all active rules for the dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM automation_rules")
        rules = cursor.fetchall()
        return {"rules": rules}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/status")
def get_system_status():
    """Returns the latest known state of all sensors and actuators for the dashboard."""
    return {
        "sensors": latest_sensor_data,
        "actuators": latest_actuator_state
    }

@app.post("/api/actuators")
def manual_actuator_control(command: ManualCommand):
    """Manually forwards an 'ON/OFF' state change to the simulator."""
    name=command.actuator_name
    target_state = command.target_state
    if not target_state:
        raise HTTPException(status_code=400, detail="State payload is required (e.g., {'state': 'ON'})")
        
    try:
        response = requests.post(
            f"{SIMULATOR_URL}/actuators/{name}",
            json={"state": target_state},
            timeout=5
        )
        response.raise_for_status()
        
        # Update local cache!
        latest_actuator_state[name] = target_state
        
        return {"status": "success", "message": f"Actuator {name} successfully turned {target_state}."}
        
    except requests.exceptions.RequestException as e:
        print(f"Simulator communication error: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Failed to communicate with simulator: {str(e)}")

@app.post("/api/rules")
def add_rule(rule: Rule):
    """Creates a new automation rule with validation."""
    
    # 1. Validation check over actuators
    valid_actuators = {"cooling_fan", "entrance_humidifier", "hall_ventilation", "habitat_heater"}
    if rule.actuator_name not in valid_actuators:
        raise HTTPException(status_code=400, detail=f"Unknown actuator '{rule.actuator_name}'. Valid are: {', '.join(valid_actuators)}")
        
    # 2. Validation check over empty sensors
    if not rule.sensor_id or not rule.sensor_id.strip():
        raise HTTPException(status_code=400, detail="Sensor ID cannot be empty.")
        
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if the rule has to be overwritten or inserted
        check_sql = "SELECT id FROM automation_rules WHERE sensor_id = %s AND operator = %s"
        cursor.execute(check_sql, (rule.sensor_id, rule.operator))
        existing_rule = cursor.fetchone()
        if existing_rule:
            delete_sql = "DELETE FROM automation_rules WHERE sensor_id = %s AND operator = %s"
            cursor.execute(delete_sql, (rule.sensor_id, rule.operator))
            print(f"Overwriting existing rule for {rule.sensor_id}: {rule.operator}", flush=True)
        
        sql = "INSERT INTO automation_rules (sensor_id, operator, threshold_value, actuator_name, target_state) VALUES (%s, %s, %s, %s, %s)"
        val = (rule.sensor_id, rule.operator, rule.threshold_value, rule.actuator_name, rule.target_state)
        cursor.execute(sql, val)
        conn.commit()
        
        return {"status": "success", "message": "Rule has been added successfully."}
    
    except mysql.connector.Error as e:
        print(f"Database error during addition: {e}", flush=True)
        raise HTTPException(status_code=500, detail="Internal server error")
    
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    """Deletes a specific automation rule from the DB."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        delete_sql = "DELETE FROM automation_rules WHERE id = %s"
        cursor.execute(delete_sql, (rule_id,))
        conn.commit()
        
        # cursor.rowcount tells us how many rows were canceled
        if cursor.rowcount > 0:
            print(f"Rule ID {rule_id} deleted successfully.", flush=True)
            return {"status": "success", "message": "Rule has been deleted successfully."}
        else:
            raise HTTPException(status_code=404, detail=f"Rule ID {rule_id} not found.")
            
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Database error during deletion: {e}", flush=True)
        raise HTTPException(status_code=500, detail="Internal server error")
        
    finally:
        cursor.close()
        conn.close()

