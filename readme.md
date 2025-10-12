# Vessel Frame
A desktop picture frame that can receive AIS messages from nearby ships and display the information

# Get Started
This code has been tested on a Raspberry Pi Zero 2W running Bookworm.
After setting up the Pi, clone the repository & open a terminal in the project root


## Set up a virtual environment
```bash
# Create the virtual env
python -m venv .venv

# Activate venv (Linux)
source .venv/bin/activate
# Activate venv (Windows)
.venv\Scripts\activate
```

## Install vf_core & plugins
```bash
pip install ./core
pip install ./plugins/message_sources/mock_message_source
```
TODO: Explanation on plugins and which ones to install

## Run the project
```bash
vf
```