# SYSTEM DESCRIPTION:

The system is a distributed automation platform built for the Mars IoT Simulator. Designed for a 2-person team, the architecture focuses exclusively on REST polling ingestion, skipping telemetry stream handling as permitted by the assignment specifics. 

The system periodically polls REST-based sensors to gather heterogeneous environmental data, normalizes these payloads into a unified standard event format, and publishes them to an internal message broker. An Automation Engine consumes these standardized events, matches them against a set of simple, user-defined, persistent "if-then" rules, and interacts natively with the Mars Simulator Actuator APIs to trigger responses (e.g., turning on the `cooling_fan` or `habitat_heater`). Finally, it serves a real-time web dashboard that gives operators situational awareness, allowing them to track the latest sensor states, control equipment, and configure the automation rules.

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

# STANDARD EVENT SCHEMA

To handle the disparity of REST sensor payloads provided by the Mars Simulator (`rest.scalar.v1`, `rest.chemistry.v1`, `rest.level.v1`, `rest.particulate.v1`), the system produces events formatted under a single Standard Schema:

```json
{
  "sensor_id": "string",
  "captured_at": "string (ISO 8601 date-time)",
  "metric": "string",
  "value": "number",
  "unit": "string",
  "status": "string (ok | warning)"
}
```

*Note: For composite payloads (e.g., chemistry or particulate) that carry multiple metrics (like `pm1_ug_m3`, `pm25_ug_m3`), the normalization layer will flatten the payload and emit independent events for each individual metric if necessary for the rule engine evaluation.*

# RULE MODEL

Automation rules are stored in a persistent database (i.e., MariaDB) to withstand service restarts.

**Logical Structure:**
`IF <sensor_id> <operator> <threshold> THEN SET <actuator_name> to <state>`

**Database Table (`automation_rules`):**
| Column | Type | Description |
|---|---|---|
| `id` | Integer | Primary Key |
| `sensor_id` | String | The sensor to evaluate (e.g., `greenhouse_temperature`) |
| `operator` | String | One of: `<`, `<=`, `=`, `>`, `>=` |
| `threshold_value` | Float | The boundary condition against the sensor's value |
| `actuator_name` | String | Target actuator to trigger (e.g., `cooling_fan`) |
| `target_state` | String | Target action state: `ON`, `OFF` |
