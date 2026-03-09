#!/bin/bash

# Load custom environment variables if the file exists
load_custom_env() {
    CUSTOM_ENV_FILE="/srv/jupyterhub/custom_env.json"
    if [ -f "$CUSTOM_ENV_FILE" ]; then
        echo "Loading custom environment variables..."
        # Parse JSON file and export variables
        python3 -c "
import json
import os
try:
    with open('$CUSTOM_ENV_FILE', 'r') as f:
        env_vars = json.load(f)
    for key, value in env_vars.items():
        print(f'export {key}=\"{value}\"')
except Exception as e:
    print(f'# Error loading custom env: {e}')
" > /tmp/custom_env.sh
        
        # Source the temporary file to export variables
        source /tmp/custom_env.sh
        
        # Clean up
        rm /tmp/custom_env.sh
        
        # Print loaded variables for debugging
        echo "Custom environment variables loaded:"
        for var in JUPYTERHUB_TIMEOUT JUPYTERHUB_USER JUPYTERHUB_PERCENTAGE_CPU JUPYTERHUB_MEMORY_LIMIT; do
            echo "$var = ${!var}"
        done
    fi
}

# Function to start all services
start_services() {
    echo "Starting all services..."
    
    # Load custom environment variables
    load_custom_env
    
    # Start JupyterHub in the background
    jupyterhub &
    JUPYTERHUB_PID=$!
    echo "JupyterHub is running with PID: $JUPYTERHUB_PID"
    
    # Start the API server
    python /srv/jupyterhub/api.py &
    API_PID=$!
    echo "API Server is running with PID: $API_PID"
    
    # (Admin panel is now merged into api.py)
}

# Function to stop all services
stop_services() {
    echo "Shutting down services..."
    
    # Kill all processes
    pkill -f "/usr/local/bin/jupyterhub"
    pkill -f "configurable-http-proxy"
    pkill -f "python /srv/jupyterhub/api.py"
    
    # Wait a moment to ensure processes are terminated
    sleep 3
    
    # More aggressive kill if any processes are still running
    pkill -9 -f "/usr/local/bin/jupyterhub"
    pkill -9 -f "configurable-http-proxy"
    pkill -9 -f "python /srv/jupyterhub/api.py"
    
    # Clean up PID files
    rm -f /srv/jupyterhub/jupyterhub-proxy.pid
    
    # Make sure ports are free
    for PORT in 8000 8001 8081 6000; do
        PID=$(netstat -tulpn 2>/dev/null | grep ":$PORT " | awk '{print $7}' | cut -d/ -f1)
        if [ ! -z "$PID" ]; then
            echo "Killing process $PID using port $PORT"
            kill -9 $PID 2>/dev/null
        fi
    done
    
    echo "All services stopped"
}

# Function to handle shutdown
cleanup() {
    stop_services
    exit 0
}

# Create a restart monitor function
restart_monitor() {
    RESTART_FILE="/srv/jupyterhub/restart_requested"
    
    while true; do
        if [ -f "$RESTART_FILE" ]; then
            echo "Restart requested..."
            
            # Remove the restart flag file immediately to prevent repeated restarts
            rm -f "$RESTART_FILE"
            
            stop_services
            sleep 2
            start_services
            
            echo "Services restarted successfully"
        fi
        sleep 1
    done
}

# Trap signals
trap cleanup SIGTERM SIGINT

# Remove any stale restart flag file at startup
rm -f /srv/jupyterhub/restart_requested

# Start services initially
start_services

# Start the restart monitor in the background
restart_monitor &
MONITOR_PID=$!

echo "Services started:"
echo "JupyterHub is running with PID: $JUPYTERHUB_PID"
echo "API Server (+ Admin panel) is running with PID: $API_PID"
echo "Restart monitor is running with PID: $MONITOR_PID"

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?