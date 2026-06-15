import cv2
import numpy as np
import os
import time
from concurrent.futures import ThreadPoolExecutor
from picamera2 import Picamera2
from picamera2.devices.imx500 import IMX500

# --- User Configuration ---
IMX500_MODEL = "imx500_network_yolo11n_pp.rpk"
TARGET_CLASS = "bird"
IMX_CONF_THRESHOLD = 0.40
CROP_PADDING = 90  

QUEUE_DIR = "queue"
HIGHRES_DIR = "highres_cache"
os.makedirs(QUEUE_DIR, exist_ok=True)
os.makedirs(HIGHRES_DIR, exist_ok=True)

# --- Tracking Rules ---
SPATIAL_THRESHOLD = 475.0  
COOLDOWN_PERIOD = 30.0     
GRACE_PERIOD = 5.0        

tracked_slots = {}  
next_slot_id = 1

# Background thread pool dedicated entirely to slow SD card I/O tasks
io_executor = ThreadPoolExecutor(max_workers=1)

# --- Load IMX500 Labels ---
try:
    with open("coco_labels.txt", "r") as f:
        coco_labels = [line.strip() for line in f.readlines()]
except FileNotFoundError:
    print("Error: coco_labels.txt not found.")
    exit()

# --- Async Write Helper ---
def save_burst_async(burst_frames, event_id, slot_id):
    """Worker function that runs in the background to prevent camera loop freezes"""
    for idx, frame_crop in enumerate(burst_frames):
        filename = f"BATCH_{event_id}_{slot_id}_{idx}.jpg"
        
        # Save high-res crop
        cv2.imwrite(os.path.join(HIGHRES_DIR, filename), frame_crop)
        
        # Resize and save low-res queue payload
        frame_low = cv2.resize(frame_crop, (640, 640))
        cv2.imwrite(os.path.join(QUEUE_DIR, filename), frame_low)

# --- Camera Initialization ---
imx = IMX500(IMX500_MODEL)
cam = Picamera2(imx.camera_num)
cam.configure(cam.create_preview_configuration(main={"size": (2028, 1520), "format": "RGB888"}))

print(f"Flashing {IMX500_MODEL} to IMX500...")
imx.show_network_fw_progress_bar()
cam.start()

cam.set_controls({
    "AeEnable": True,
    "ExposureTime": 3333   
})

print("[-] Asynchronous Native Engine Active (Zero-Freeze). Press 'q' to quit.")

try:
    while True:
        req = cam.capture_request()
        meta = req.get_metadata()
        current_time = time.time()
        
        out = imx.get_outputs(meta)
        current_birds = []
        bird_detected_this_frame = False

        # ===========================================================================
        # PHASE 1: HARDWARE BOXES & HIGH-RES CROPPING
        # ===========================================================================
        if out is not None and len(out) >= 3:
            boxes = np.atleast_2d(np.squeeze(out[0]))
            scores = np.atleast_1d(np.squeeze(out[1]))
            classes = np.atleast_1d(np.squeeze(out[2]))
            
            for i in range(len(scores)):
                conf = float(scores[i])
                class_id = int(classes[i])
                class_name = coco_labels[class_id] if class_id < len(coco_labels) else "unknown"
                
                if conf > IMX_CONF_THRESHOLD and class_name == TARGET_CLASS:
                    bird_detected_this_frame = True
                    break 
            
            if bird_detected_this_frame:
                frame = req.make_array("main")
                
                for i in range(len(scores)):
                    conf = float(scores[i])
                    class_id = int(classes[i])
                    class_name = coco_labels[class_id] if class_id < len(coco_labels) else "unknown"
                    
                    if conf > IMX_CONF_THRESHOLD and class_name == TARGET_CLASS:
                        xmin, ymin, xmax, ymax = boxes[i]
                        
                        if xmax <= 1.0 and ymax <= 1.0:
                            xmin, xmax = xmin * 640, xmax * 640
                            ymin, ymax = ymin * 640, ymax * 640
                        
                        y_padding_640 = (640 - 480) / 2
                        ymin, ymax = ymin - y_padding_640, ymax - y_padding_640
                        
                        scale_factor = 2028.0 / 640.0  
                        
                        x1 = max(0, int(xmin * scale_factor))
                        y1 = max(0, int(ymin * scale_factor))
                        x2 = min(2028, int(xmax * scale_factor))
                        y2 = min(1520, int(ymax * scale_factor))
                        
                        if x1 >= x2 or y1 >= y2:
                            continue
                        
                        cx = (x1 + x2) / 2.0
                        cy = (y1 + y2) / 2.0
                        
                        crop_x1, crop_y1 = max(0, x1 - CROP_PADDING), max(0, y1 - CROP_PADDING)
                        crop_x2, crop_y2 = min(2028, x2 + CROP_PADDING), min(1520, y2 + CROP_PADDING)
                        
                        highres_crop = frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()
                        if highres_crop.size == 0:
                            continue
                            
                        current_birds.append({
                            'center': (cx, cy),
                            'crop': highres_crop
                        })

        # ===========================================================================
        # PHASE 2: TRACKING & BURST ASSEMBLY
        # ===========================================================================
        taken_slots = set() 
        
        for bird in current_birds:
            matched_slot_id = None
            min_dist = float('inf')
            
            for slot_id, slot in tracked_slots.items():
                if slot_id in taken_slots:
                    continue
                    
                dist = np.hypot(bird['center'][0] - slot['center'][0], bird['center'][1] - slot['center'][1])
                if dist < min_dist and dist < SPATIAL_THRESHOLD:
                    min_dist = dist
                    matched_slot_id = slot_id

            if matched_slot_id is None:
                active_slot_id = next_slot_id
                next_slot_id += 1
                
                tracked_slots[active_slot_id] = {
                    'center': bird['center'],
                    'last_seen': current_time,
                    'cooldown_until': current_time + COOLDOWN_PERIOD,
                    'gathering_burst': True,
                    'event_id': int(current_time * 1000),
                    'burst_frames': []
                }
                taken_slots.add(active_slot_id)
                print(f"[*] Slot {active_slot_id}: Arrival detected. Gathering 5-frame burst...")
                
            else:
                active_slot_id = matched_slot_id
                slot = tracked_slots[active_slot_id]
                slot['center'] = bird['center'] 
                slot['last_seen'] = current_time 
                taken_slots.add(active_slot_id)
                
                if current_time >= slot['cooldown_until'] and not slot.get('gathering_burst'):
                    slot['gathering_burst'] = True
                    slot['event_id'] = int(current_time * 1000)
                    slot['burst_frames'] = []
                    slot['cooldown_until'] = current_time + COOLDOWN_PERIOD
                    print(f"[*] Slot {active_slot_id}: Cooldown expired. Gathering new burst...")

            slot = tracked_slots[active_slot_id]
            if slot.get('gathering_burst'):
                slot['burst_frames'].append(bird['crop'])
                
                if len(slot['burst_frames']) >= 5:
                    # Offload the slow save process entirely to the background thread
                    io_executor.submit(
                        save_burst_async, 
                        slot['burst_frames'].copy(), 
                        slot['event_id'], 
                        active_slot_id
                    )
                    
                    print(f"[+] Slot {active_slot_id}: 5-frame burst offloaded to background writer.")
                    slot['gathering_burst'] = False
                    slot['burst_frames'] = []

        # ===========================================================================
        # PHASE 3: PRUNE DEAD SLOTS 
        # ===========================================================================
        dead_slots = [sid for sid, s in tracked_slots.items() if (current_time - s['last_seen']) > GRACE_PERIOD]
        for sid in dead_slots:
            del tracked_slots[sid]
            print(f"[-] Slot {sid}: Bird left the feeder.")

        req.release()

finally:
    cam.stop()
    io_executor.shutdown(wait=True)
