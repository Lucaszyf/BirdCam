# BirdCam
YOLO11 AI image recognition for birds deployed on a Raspberry Pi (Zero or 5) and an AI Camera

## System Architecture

* **Camera:** Raspberry Pi AI Camera Module
* **Edge Processing:** Raspberry Pi Zero 2 W or Raspberry Pi 5
* **Cloud Backend:** VPS hosting a custom Webhook receiver and web gallery, or hosted locally on the Pi

## Prerequisites

To get this running on a fresh Raspberry Pi OS install, open your terminal and run these commands sequentially. This will update your system, install the necessary Sony IMX500 AI Camera firmware, and set up your Python environment.

```bash
# 1. Update the Raspberry Pi OS to the latest software
sudo apt update && sudo apt full-upgrade -y

# 2. Install the IMX500 hardware drivers, Picamera2, and OpenCV
sudo apt install imx500-all python3-picamera2 python3-opencv -y

# 3. Install the required AI and web Python packages
pip3 install ultralytics flask requests --break-system-packages

# 4. Reboot the Pi to load the IMX500 kernel drivers
sudo reboot
```
## Installation

Once your Raspberry Pi has rebooted, open a new terminal to download the project files.

```bash
# 1. Clone the repository to your Raspberry Pi
git clone [https://github.com/Lucaszyf/birdcam.git](https://github.com/Lucaszyf/birdcam.git)

# 2. Navigate into the automatically created project folder
cd birdcam
```
**⚠️ Configuration Note**
Before running the pipeline, you **must** configure your notification and viewing endpoints based on your setup.

### Option A: Hosting with a Cloud VPS
If you are deploying this with a remote server, your web dashboard code (`vps_app.py`) runs directly on your VPS. It acts as a middleman: catching frames from the Raspberry Pi, saving them for the web gallery, and forwarding alerts to Discord.

1. **Install VPS Prerequisites:** Run this command in your VPS terminal to install the minimal Python dependencies required to host the dashboard:
   ```bash
   pip3 install flask requests
   ```
2. Open `vps_app.py` on your server and update your `DISCORD_WEBHOOK_URL` and `VPS_PUBLIC_URL` near the top of the script
3. Open `analyze.py` on your Raspberry Pi and modify the `VPS_WEBHOOK_URL` to your VPS webhook route and replace `GALLERY_URL` with your `VPS_PUBLIC_URL` from the previous step

### Option B: Hosting Locally on Pi
If you don't have a VPS, you can still use Discord for free mobile alerts and host the Flask web gallery directly on your Raspberry Pi within your home network. Because the edge script is natively compatible with Discord's API, setup is completely plug-and-play.

1. Open `analyze.py` on your Raspberry Pi and modify the variables at the top of the file:
   * Change `VPS_WEBHOOK_URL` to your actual **Discord Webhook URL**.
   * Change `GALLERY_URL` to your Raspberry Pi's local network IP address (e.g., `http://192.168.1.50:5000`) so devices on your Wi-Fi can click the link in Discord to open the gallery.

## Running the Pipeline
To run the camera stream and the AI processing simultaneously, you need to execute the scripts in **two separate terminal windows** (or two separate SSH sessions).

### Terminal Window 1: Start the Camera Capture
Run the capture script to begin monitoring the AI Camera feed using Picamera2 and caching image bursts.
```bash
python capture.py
```
### Terminal Window 2: Start the AI Analyzer
In a separate window, run the analyzer script to process incoming image batches and evaluate detections using the YOLO11 model. **The script may take a few minutes to boot.**
```bash
python analyze.py
```
### Terminal Window 3: Start the Web Dashboard
To view your captured bird visitors on the web interface, launch the dashboard according to your setup:
* If using Option A (Cloud VPS): Run the script directly on your remote server terminal:
```bash
python3 vps_app.py
```
* If using Option B (Hosting locally on Pi): Open a third terminal window on your Raspberry Pi and run the local app script to host the webpage on your home network.
```bash
python3 app.py
```
