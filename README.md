# Mars IoT Dashboard
## Overview
The following repository contains all the material related to the hackathon held from March 6<sup>th</sup> 2026 to March 10<sup>th</sup> 2026 for the course of Laboratory in Advanced Programming, held by Sapienza University of Rome.

## Abstract
The goal of the hackathon is to build a system capable of ingesting and normalizing data (through a Unified Event Schema) from a simulated IoT environment on Mars, and use these data to enforce some automation rules and to provide a real-time monitoring dashboard. Further technical details are available for reading in the `booklets/` directory.

## Members
- Luca Di Carlo [dicarlo.2045541@studenti.uniroma1.it]
- Gabriele Bruni [bruni.2056777@studenti.uniroma1.it]

## Chosen frameworks
- Python 3 (with FastAPI, Jinja2Templates, Requests, pika)
- RabbitMQ
- MariaDB
- HTML5, Vanilla JS and Bootstrap
- Docker and docker-compose

## Additional information
The simulator container is given in the form of a .tar file, and in order to make the system work, it has to be loaded.
The loading step of this container depends on the operating system:
- in case of Windows, you must enable the following flag in Docker Desktop > Settings > General > [x] Use containerd for pulling and storing images;
- in case of a Linux distribution, you should launch the following command via shell `sudo ctr -n moby images import <path to .tar container>`.
