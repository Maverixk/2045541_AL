# SYSTEM DESCRIPTION:

The system is a distributed automation platform designed for Mars habitat survival. It utilizes a microservices architecture to poll heterogeneous REST sensors from a provided IoT simulator, normalize the data into a unified format, and manage automation rules. Communication between data ingestion and logic is decoupled via a message broker to ensure scalability and fault tolerance.

# USER STORIES:

1) As an Operator, I want to see a real-time dashboard with the latest sensor values so that I can monitor the habitat conditions.
2) As an Operator, I want to view the current status of all actuators so that I know what equipment is currently operating.
3) As an Operator, I want to manually switch actuators ON or OFF from the dashboard so that I can intervene when necessary.
4) As an Operator, I want to create an automation rule from the dashboard so that the system can react automatically to sensor changes.
5) As an Operator, I want to view the list of active automation rules so that I know what behaviors are currently configured.
6) As an Operator, I want to delete an existing automation rule so that I can remove obsolete behaviors.
7) As the System, I want to poll data from REST sensors periodically so that the latest environmental data is seamlessly fetched.
8) As the System, I want to normalize the varying payloads from different REST sensors into a unified event format so that downstream services can process them uniformly.
9) As the System, I want to evaluate incoming sensor events dynamically against persisted rules so that the system safely triggers actuators when environmental conditions change.
10) As the System, I want to persist the created automation rules in an internal database so that they survive system restarts.


# CONTAINERS:

## CONTAINER_NAME: simulator

### DESCRIPTION: 
IoT simulation environment that generates the environmental telemetry of the Martian base and exposes endpoints for reading sensors and writing to actuators.

### USER STORIES:
7) As the System, I want to poll data from REST sensors periodically so that the latest environmental data is seamlessly fetched.
9) As the System, I want to evaluate incoming sensor events dynamically against persisted rules so that the system safely triggers actuators when environmental conditions change.

### PORTS: 
8080:8080

### DESCRIPTION:
The simulator container acts as the physical environment of the Martian base. It manages the entire simulation logic of the physical world, providing the domain's contractual API (third-party service provided as an OCI image).

### PERSISTENCE EVALUATION
The simulator container does not require data persistence. Data is ephemeral and generated at runtime during the simulation. 

### EXTERNAL SERVICES CONNECTIONS
The simulator container does not connect to external services. It acts as a passive data source (REST Server).

### MICROSERVICES:

#### MICROSERVICE: mars-iot-simulator
- TYPE: backend
- DESCRIPTION: Generates telemetry data and exposes REST endpoints for sensors and actuators.
- PORTS: 8080
- TECHNOLOGICAL SPECIFICATION:
Pre-built OCI image (`mars-iot-simulator:multiarch_v1`).
- SERVICE ARCHITECTURE:
Black-box simulator acting as the primary data source and actuator target for the ecosystem.


## CONTAINER_NAME: message_broker

### DESCRIPTION: 
RabbitMQ message broker used to manage asynchronous queues and decouple the data reading phase from the processing phase.

### USER STORIES:
8) As the System, I want to normalize the varying payloads from different REST sensors into a unified event format so that downstream services can process them uniformly.
9) As the System, I want to evaluate incoming sensor events dynamically against persisted rules so that the system safely triggers actuators when environmental conditions change.

### PORTS: 
5672:5672
15672:15672

### DESCRIPTION:
The message_broker container implements the publish/subscribe and producer/consumer patterns (AMQP). It provides reliability and buffering for both raw payloads and normalized data across the internal Docker network.

### PERSISTENCE EVALUATION
The message_broker container requires persistent storage. It uses the Docker Named Volume `rabbitmq_data` mounted on `/var/lib/rabbitmq` to preserve the state of queues, pending messages, and cluster definitions even in the event of a container crash or restart.

### EXTERNAL SERVICES CONNECTIONS
The message_broker container does not connect to external services. It receives TCP connections from the internal containers `ingestion`, `normalization`, and `automation_engine`.

### MICROSERVICES:

#### MICROSERVICE: rabbitmq
- TYPE: middleware
- DESCRIPTION: Message broker handling AMQP queues (`raw_sensors_data`, `normalized_events`).
- PORTS: 5672, 15672
- TECHNOLOGICAL SPECIFICATION:
Official `rabbitmq:3-management` image. Erlang-based message broker with a built-in HTTP management dashboard.
- SERVICE ARCHITECTURE:
Middleware component acting as the central nervous system for asynchronous event distribution between the ingestion, normalization, and logic layers.


## CONTAINER_NAME: database

### DESCRIPTION: 
MariaDB relational database used to store historical normalized data and automation rule configurations.

### USER STORIES:
4) As an Operator, I want to create an automation rule from the dashboard so that the system can react automatically to sensor changes.
5) As an Operator, I want to view the list of active automation rules so that I know what behaviors are currently configured.
6) As an Operator, I want to delete an existing automation rule so that I can remove obsolete behaviors.
10) As the System, I want to persist the created automation rules in an internal database so that they survive system restarts.

### PORTS: 
3307:3306

### DESCRIPTION:
The database container serves as the central manager of structured persistence. Safe startup is guaranteed by a native healthcheck script (`healthcheck.sh --connect --innodb_initialized`) that blocks the startup of dependent services until the InnoDB engine is fully initialized.

### PERSISTENCE EVALUATION
The database container requires highly persistent storage. It uses the Docker Named Volume `mariadb_data` mounted on `/var/lib/mysql` to preserve schemas, tables, and tuples long-term.

### EXTERNAL SERVICES CONNECTIONS
The database container does not connect to external services. It receives SQL queries exclusively from the `automation_engine` container.

### MICROSERVICES:

#### MICROSERVICE: mariadb
- TYPE: database
- DESCRIPTION: Stores all relevant data concerning automation rules.
- PORTS: 3306 (Internal), 3307 (Host)
- TECHNOLOGICAL SPECIFICATION:
Official `mariadb:lts` image. Relational database management system utilizing SQL for data storage and retrieval.
- SERVICE ARCHITECTURE:
Centralized data storage layer supporting the business logic of the automation engine.

- DB STRUCTURE: 

	`automation_rules` : | **_id_** | sensor_id | operator | threshold_value | actuator_name | target_state |

## CONTAINER_NAME: ingestion

### DESCRIPTION: 
Worker service that implements a polling loop to query the simulator's REST APIs and send the raw payloads to the message broker queue.

### USER STORIES:
7) As the System, I want to poll data from REST sensors periodically so that the latest environmental data is seamlessly fetched.

### PORTS: 
No exposed ports.

### DESCRIPTION:
The ingestion container acts as a pure AMQP producer. It performs cyclical HTTP GET requests to extract the map of available sensors and iterates over each of them at regular intervals, pushing raw JSON responses into the message broker without concerning itself with their internal structure.

### PERSISTENCE EVALUATION
The ingestion container is completely stateless. It processes data in memory and delegates all persistence to RabbitMQ.

### EXTERNAL SERVICES CONNECTIONS
The ingestion container does not connect to external services. It connects internally via HTTP to `simulator` and via AMQP to `message_broker`.

### MICROSERVICES:

#### MICROSERVICE: data-ingestion-worker
- TYPE: backend
- DESCRIPTION: Python script designed for sensor integration via REST protocol and raw forwarding over asynchronous messaging.
- PORTS: None
- TECHNOLOGICAL SPECIFICATION:
Developed in Python 3.11. Uses the `requests` library for REST HTTP queries and the `pika` library for persistent AMQP connections to RabbitMQ. Output is unbuffered for real-time logging.
- SERVICE ARCHITECTURE:
Poller / Producer type worker. It executes continuous background loops to fetch data and immediately pushes it to the `raw_sensors_data` queue.


## CONTAINER_NAME: normalization

### DESCRIPTION: 
Worker service that consumes heterogeneous raw messages, applies the simulator's Schema Contracts, and transforms them into the internal domain standard.

### USER STORIES:
8) As the System, I want to normalize the varying payloads from different REST sensors into a unified event format so that downstream services can process them uniformly.

### PORTS: 
No exposed ports.

### DESCRIPTION:
The normalization container acts as an Event Processor. It filters and remaps disjointed JSON fields from various sensor types (scalar, chemistry, level) into a single "Unified Event Schema", publishing the cleaned data back into a new broker queue.

### PERSISTENCE EVALUATION
The normalization container is completely stateless. It uses RAM for string/JSON manipulation operations during message transit.

### EXTERNAL SERVICES CONNECTIONS
The normalization container does not connect to external services. It connects exclusively to the `message_broker`.

### MICROSERVICES:

#### MICROSERVICE: schema-normalizer
- TYPE: backend
- DESCRIPTION: Model adapter that resolves the fragmentation of data schemas by transforming them into a single standard format.
- PORTS: None
- TECHNOLOGICAL SPECIFICATION:
Developed in Python 3.11. Uses the `json` module for payload manipulation and `pika` for asynchronous event management and messaging ACKs.
- SERVICE ARCHITECTURE:
Message Translator / Pipe-and-Filter type worker. Consumes events from `raw_sensors_data`, maps them, and injects them into `normalized_events`.


## CONTAINER_NAME: automation_engine

### DESCRIPTION: 
The logical and decision-making core of the system. It evaluates rules, processes alarms, manages actuators, and offers external API services.

### USER STORIES:
3) As an Operator, I want to manually switch actuators ON or OFF from the dashboard so that I can intervene when necessary.
4) As an Operator, I want to create an automation rule from the dashboard so that the system can react automatically to sensor changes.
5) As an Operator, I want to view the list of active automation rules so that I know what behaviors are currently configured.
6) As an Operator, I want to delete an existing automation rule so that I can remove obsolete behaviors.
9) As the System, I want to evaluate incoming sensor events dynamically against persisted rules so that the system safely triggers actuators when environmental conditions change.

### PORTS: 
8000:8000

### DESCRIPTION:
The automation_engine container acts as an orchestrator middleware. It subscribes to normalized telemetry events, archives them in the database, checks threshold conditions in real-time against stored rules, and sends REST commands to the simulator. It also serves as the REST API backend for the frontend dashboard.

### PERSISTENCE EVALUATION
The automation_engine container is stateless regarding data storage, but it implements database reads and writes to the `database` container, delegating total rule persistence to it.

### EXTERNAL SERVICES CONNECTIONS
The automation_engine container does not connect to external services. It connects internally to `message_broker` (consume), `database` (I/O), and `simulator` (HTTP POST).

### MICROSERVICES:

#### MICROSERVICE: core-automation-backend
- TYPE: backend
- DESCRIPTION: REST API server and background event handler for Martian base automation and rule evaluation.
- PORTS: 8000
- TECHNOLOGICAL SPECIFICATION:
Built using Python 3.11 and the FastAPI framework, served via ASGI Uvicorn. Utilizes `pika` for background interception of AMQP events, and MySQL/MariaDB driver libraries for SQL queries.
- SERVICE ARCHITECTURE:
Distributed modular monolith: integrates a REST Controller layer for the UI, a Service layer for DB management, and an asynchronous Event Subscriber layer.

- ENDPOINTS: 
		
	| HTTP METHOD | URL | Description | User Stories |
	| ----------- | --- | ----------- | ------------ |
    | GET | /api/status | Returns current metrics and the status of sensors actuators. | 1, 2 |
    | GET | /api/rules | Returns the list of active automation rules read from the DB. | 5 |
    | POST | /api/rules | Adds a new automation rule to the DB. | 4 |
    | POST | /api/actuators | Manually forwards an "ON/OFF" state change to the simulator. | 3 |
	| DELETE | /api/rules/{id} | Deletes a specific rule from the DB. | 6 |


## CONTAINER_NAME: frontend

### DESCRIPTION: 
Web user interface to monitor sensors and allow manual control of Martian parameters by the human operator.

### USER STORIES:
1) As an Operator, I want to see a real-time dashboard with the latest sensor values so that I can monitor the habitat conditions.
2) As an Operator, I want to view the current status of all actuators so that I know what equipment is currently operating.
3) As an Operator, I want to manually switch actuators ON or OFF from the dashboard so that I can intervene when necessary.
4) As an Operator, I want to create an automation rule from the dashboard so that the system can react automatically to sensor changes.
5) As an Operator, I want to view the list of active automation rules so that I know what behaviors are currently configured.
6) As an Operator, I want to delete an existing automation rule so that I can remove obsolete behaviors.

### PORTS: 
8001:8001

### DESCRIPTION:
The frontend container is a pure presentation layer service. It dynamically fetches metrics, actuator statuses, and rules from the RESTful backend APIs and provides an interactive UI without processing heavy logical computations.

### PERSISTENCE EVALUATION
The frontend container does not include a database and is completely stateless. It renders HTML views based on data returned by the backend APIs.

### EXTERNAL SERVICES CONNECTIONS
The frontend container does not connect to external services. It communicates exclusively via HTTP requests toward the `automation_engine` utilizing internal DNS (`LOGIC_API_URL=http://automation_engine:8000`).

### MICROSERVICES:

#### MICROSERVICE: web-dashboard-ui
- TYPE: frontend
- DESCRIPTION: Interactive web platform for astronauts to administer the simulated environment.
- PORTS: 8001
- TECHNOLOGICAL SPECIFICATION:
Python 3.11 using FastAPI/Uvicorn to serve files. Employs the Jinja2 templating engine, HTML5, and basic CSS/JS for the client-side presentation.
- SERVICE ARCHITECTURE:
Server-Side Rendering (SSR) or Single Page Application interacting directly with the backend API layer.

- PAGES: 

	| Name | Description | Related Microservice | User Stories |
	| ---- | ----------- | -------------------- | ------------ |
	| Dashboard / Home | Displays the list of sensors, recent values, and On/Off buttons for actuators. | core-automation-backend | 1, 2, 3 |
	| Rules Editor | Module to view, insert, or delete autonomous automation logic rules. | core-automation-backend | 4, 5, 6 |