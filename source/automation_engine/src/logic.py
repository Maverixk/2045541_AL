import os
import json
import time
import requests
import pika
import mysql.connector
from pydantic import BaseModel

# Environment variables
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
SIMULATOR_URL = os.getenv("SIMULATOR_URL")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")


INPUT_QUEUE = "normalized_sensors_data"

# In-memory cache
latest_sensor_data = {}
latest_actuator_state = {}


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

def init_db():
    """Create the tables if they don't exist."""
    print("Checking and creating necessary DB tables...", flush=True)
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS automation_rules (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sensor_id VARCHAR(255) NOT NULL,
                    operator VARCHAR(10) NOT NULL,
                    threshold_value FLOAT NOT NULL,
                    actuator_name VARCHAR(255) NOT NULL,
                    target_state VARCHAR(10) NOT NULL
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
            print("Database initialized successfully.", flush=True)
            break
        except mysql.connector.Error as e:
            print(f"Database not ready yet, retrying... Error: {e}", flush=True)
            time.sleep(3)

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
        
        if "actuators" in actuators_data:
            latest_actuator_state.update(actuators_data["actuators"])
        elif isinstance(actuators_data, dict):
            latest_actuator_state.update(actuators_data)   

    except requests.exceptions.RequestException as e:
        print(f"Simulator communication error: {e}", flush=True)