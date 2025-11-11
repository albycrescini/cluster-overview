#!/bin/bash

set -e

if [ -n "$VIRTUAL_ENV" ]; then
    echo "Virtual environment is already active: $VIRTUAL_ENV"
    exit 0
fi

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Please install it first."
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is not installed. Please install it first."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists"
fi

# Install requirements
echo "Installing requirements..."
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

# Make script executable if it exists
if [ -f "script.py" ]; then
    chmod +x script.py
fi

echo ""
echo "Virtual environment is ready. To activate it, run:"
echo "source venv/bin/activate"
echo "Then you can run: ./script.py <cluster> <namespace>"
