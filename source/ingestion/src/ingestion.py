import time
import json
import requests
import pika
import os
import sys

# Loading environment variables
SIMULATOR_URL = os.getenv("SIMULATOR_URL")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
QUEUE_NAME = "raw_sensors_data"
POLLING_INTERVAL = 5 

def connect_to_rabbitmq():
    """Tries to connect to RabbitMQ with automatic retry."""
    while True:
        try:
            params = pika.ConnectionParameters(host=RABBITMQ_HOST)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            # Making the queue 'durable' so that no data is lost in case of broker restart
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            print(f"Connected to RabbitMQ on host: {RABBITMQ_HOST}", flush=True)
            return connection, channel
        except pika.exceptions.AMQPConnectionError:
            print("RabbitMQ not ready yet... wait 3 seconds", flush=True)
            time.sleep(3)

def run_ingestion():
    f"Continuous polling from the sensors via REST every {POLLING_INTERVAL} seconds."
    print(f"Start polling from simulator: {SIMULATOR_URL}", flush=True)
    
    connection, channel = connect_to_rabbitmq()

    while True:
        try:
            # 1. Retrieving data from simulator via REST
            response = requests.get(SIMULATOR_URL, timeout=5)
            response.raise_for_status() # Raise exception in case of negative answer
            
            sensors_list = response.json().get("sensors", [])

            read_sensors = 0
            # 2. Pubblication via RabbitMQ
            for sensor_name in sensors_list:
                sensor_url = f"{SIMULATOR_URL}/{sensor_name}"
                
                try:
                    # Polling single sensor
                    sensor_response = requests.get(sensor_url, timeout=3)
                    sensor_response.raise_for_status()
                    sensor_data = sensor_response.json()
                    
                    # Pubblishing raw data on RabbitMQ
                    channel.basic_publish(
                        exchange='',
                        routing_key=QUEUE_NAME,
                        body=json.dumps(sensor_data),
                        properties=pika.BasicProperties(
                            delivery_mode=pika.DeliveryMode.Persistent,
                        )
                    )
                    read_sensors += 1

                except requests.exceptions.RequestException as e:
                    print(f"Error reading sensor {sensor_name}: {e}", flush=True)
            
            print(f"Data packets successfully sent to the broker (Read sensors: {read_sensors})", flush=True)

        except requests.exceptions.RequestException as e:
            print(f"Simulator connection error: {e}", flush=True)
        except pika.exceptions.AMQPConnectionError:
            print("Lost connection to RabbitMQ. Trying to reconnect...", flush=True)
            connection, channel = connect_to_rabbitmq()
        except Exception as e:
            print(f"Unexpected error: {e}", flush=True)

        time.sleep(POLLING_INTERVAL)

def main():
    # Waiting for other services
    time.sleep(5)
    try:
        run_ingestion()
    except KeyboardInterrupt:
        print("\nService interrupted by the user.")
        sys.exit(0)

if __name__ == "__main__":
    main()