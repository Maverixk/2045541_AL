import os
import json
import time
import threading
import requests
import pika
import mysql.connector
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Environment variables
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
SIMULATOR_URL = os.getenv("SIMULATOR_URL")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")


INPUT_QUEUE = "normalized_sensors_data"
latest_sensor_data = {}
latest_actuator_state = {}

app = FastAPI(title="Mars Automation Engine")

# Pydantic model for rules and manual commands
class Rule(BaseModel):
    sensor_id: str
    operator: str
    threshold_value: float
    actuator_name: str
    target_state: str

class ManualCommand(BaseModel):
    actuator_name: str
    target_state: str

# DB connection
def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        port=3306
    )

# Rules evaluation executed in background
def evaluate_rules(event):
    """Checks if the received event triggers some rule(s) in the DB."""
    sensor_id = event.get("sensor_id")
    value = event.get("value")
    
    if sensor_id is None or value is None:
        return

    latest_sensor_data[sensor_id] = event

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch all rules associated to that sensor
        cursor.execute("SELECT * FROM automation_rules WHERE sensor_id = %s", (sensor_id,))
        rules = cursor.fetchall()
        
        for rule in rules:
            trigger = False
            op = rule["operator"]
            threshold = rule["threshold_value"]
            
            # Operator evaluation
            if op == '>' and value > threshold: trigger = True
            elif op == '<' and value < threshold: trigger = True
            elif op == '>=' and value >= threshold: trigger = True
            elif op == '<=' and value <= threshold: trigger = True
            elif op == '==' and value == threshold: trigger = True
            
            if trigger:
                actuator = rule["actuator_name"]
                state = rule["target_state"]

                # If the actuator is already in the desired state, then do nothing!
                if latest_actuator_state.get(actuator) == state:
                    continue

                print(f"Rule triggered! {sensor_id} ({value}) {op} {threshold}. {actuator} state -> {state}", flush=True)
                
                # Sends command to the actuator 
                try:
                    response = requests.post(
                        f"{SIMULATOR_URL}/actuators/{actuator}",
                        json={"state": state},
                        timeout=5
                    )
                    response.raise_for_status()

                    latest_actuator_state[actuator] = state

                except requests.exceptions.RequestException as e:
                    print(f"Simulator communication error: {e}", flush=True)

    except Exception as e:
        print(f"DB evaluation error: {e}", flush=True)
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

# RabbitMQ worker
def rabbitmq_worker():
    """Listens to the queue of normalized data and passes them over for evaluation."""
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            channel = connection.channel()
            channel.queue_declare(queue=INPUT_QUEUE, durable=True)
            
            def callback(ch, method, properties, body):
                event = json.loads(body)
                evaluate_rules(event)
                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=INPUT_QUEUE, on_message_callback=callback)
            print("Automation Engine connected to RabbitMQ. Listening...", flush=True)
            channel.start_consuming()
            
        except pika.exceptions.AMQPConnectionError:
            print("Lost connection to RabbitMQ. Retrying in 5s...", flush=True)
            time.sleep(5)

def load_actuators_state():
    try:
        response = requests.get(f"{SIMULATOR_URL}/actuators", timeout=5)
        response.raise_for_status()

        actuators_data = response.json()
        
        if isinstance(actuators_data, dict):
            for actuator_name, state in actuators_data.items():
                latest_actuator_state[actuator_name] = state      

    except requests.exceptions.RequestException as e:
        print(f"Simulator communication error: {e}", flush=True)

# Worker starts on API startup
@app.on_event("startup")
def startup_event():
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

@app.post("/api/add_rule")
def add_rule(rule: Rule):
    """Create a new automation rule from the frontend."""
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
    finally:
        cursor.close()
        conn.close()