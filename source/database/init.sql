-- Create database (if it does not exist)
CREATE DATABASE IF NOT EXISTS mars_automation;
USE mars_automation;

-- Automation rules table
CREATE TABLE IF NOT EXISTS automation_rules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sensor_id VARCHAR(30) NOT NULL,
    operator VARCHAR(2) NOT NULL,
    threshold_value FLOAT NOT NULL,
    actuator_name VARCHAR(30) NOT NULL,
    target_state VARCHAR(3) NOT NULL
);

-- Default rules for testing purposes
INSERT INTO automation_rules (sensor_id, operator, threshold_value, actuator_name, target_state) VALUES 
('greenhouse_temperature', '>', 30.0, 'cooling_fan', 'ON'),
('co2_hall', '>', 1000.0, 'hall_ventilation', 'ON');