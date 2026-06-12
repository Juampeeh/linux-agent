#!/bin/bash
curl -s -X POST http://localhost:7860/api/sentinel -H "Content-Type: application/json" -d '{"accion":"start"}' >> /home/test/linux_agent/server.log 2>&1
