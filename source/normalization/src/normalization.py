import json
import os
import sys
import time
import pika

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "message_broker")
INPUT_QUEUE = "raw_sensors_data"
OUTPUT_QUEUE = "normalized_sensors_data"

def connect_to_rabbitmq():
    """Tries to connect to RabbitMQ with automatic retry."""
    while True:
        try:
            params = pika.ConnectionParameters(host=RABBITMQ_HOST)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            # Declare queues
            channel.queue_declare(queue=INPUT_QUEUE, durable=True)
            channel.queue_declare(queue=OUTPUT_QUEUE, durable=True)
            print(f"[Normalization] Connected to RabbitMQ on {RABBITMQ_HOST}", flush=True)
            return connection, channel
        except pika.exceptions.AMQPConnectionError:
            print("[Normalization] RabbitMQ not ready yet... wait 3 seconds", flush=True)
            time.sleep(3)

def process_and_publish(channel, raw_msg):
    """
    Parses the raw JSON payload and flattens it into zero or more normalized events.
    """
    events = []
    
    sensor_id = raw_msg.get("sensor_id")
    captured_at = raw_msg.get("captured_at")
    status = raw_msg.get("status")
    
    if not (sensor_id and captured_at and status):
        print(f"[Normalization] Skipping invalid/missing base fields: {raw_msg}", flush=True)
        return

    # 1. Scalar (rest.scalar.v1)
    if "metric" in raw_msg and "value" in raw_msg and "unit" in raw_msg:
        events.append({
            "sensor_id": sensor_id,
            "captured_at": captured_at,
            "metric": raw_msg["metric"],
            "value": raw_msg["value"],
            "unit": raw_msg["unit"],
            "status": status
        })
        
    # 2. Chemistry (rest.chemistry.v1)
    elif "measurements" in raw_msg and isinstance(raw_msg["measurements"], list):
        for meas in raw_msg["measurements"]:
            events.append({
                "sensor_id": sensor_id,
                "captured_at": captured_at,
                "metric": meas.get("metric", "unknown"),
                "value": meas.get("value", 0.0),
                "unit": meas.get("unit", ""),
                "status": status
            })
            
    # 3. Particulate (rest.particulate.v1)
    elif "pm1_ug_m3" in raw_msg or "pm25_ug_m3" in raw_msg or "pm10_ug_m3" in raw_msg:
        pm_keys = {"pm1_ug_m3": "pm1", "pm25_ug_m3": "pm2.5", "pm10_ug_m3": "pm10"}
        for key, metric_name in pm_keys.items():
            if key in raw_msg:
                events.append({
                    "sensor_id": sensor_id,
                    "captured_at": captured_at,
                    "metric": metric_name,
                    "value": raw_msg[key],
                    "unit": "ug/m3",
                    "status": status
                })
                
    # 4. Level (rest.level.v1)
    elif "level_pct" in raw_msg or "level_liters" in raw_msg:
        if "level_pct" in raw_msg:
            events.append({
                "sensor_id": sensor_id,
                "captured_at": captured_at,
                "metric": "level",
                "value": raw_msg["level_pct"],
                "unit": "%",
                "status": status
            })
        if "level_liters" in raw_msg:
            events.append({
                "sensor_id": sensor_id,
                "captured_at": captured_at,
                "metric": "volume",
                "value": raw_msg["level_liters"],
                "unit": "L",
                "status": status
            })
            
    else:
        print(f"[Normalization] Unknown schema format for payload: {raw_msg}", flush=True)

    # Publish normalized events
    for event in events:
        channel.basic_publish(
            exchange='',
            routing_key=OUTPUT_QUEUE,
            body=json.dumps(event),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
            )
        )
    if events:
        print(f"[Normalization] Standardized and forwarded {len(events)} events for {sensor_id}", flush=True)

def callback(channel, method, properties, body):
    try:
        raw_msg = json.loads(body.decode('utf-8'))
        process_and_publish(channel, raw_msg)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"[Normalization] Error processing message: {e}", flush=True)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def run():
    print("[Normalization] Service starting...", flush=True)
    time.sleep(5)
    
    connection, channel = connect_to_rabbitmq()
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=INPUT_QUEUE, on_message_callback=callback)
    
    print("[Normalization] Waiting for raw messages. To exit press CTRL+C", flush=True)
    channel.start_consuming()

if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print("\n[Normalization] Service interrupted.")
        sys.exit(0)
