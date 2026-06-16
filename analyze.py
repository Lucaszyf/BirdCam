#!/usr/bin/env python3
import os
import time
import subprocess
import shutil
import requests

# Hardware requirement for Pi Zero
os.environ["OMP_NUM_THREADS"] = "1"
import torch
torch.set_num_threads(1)

from ultralytics import YOLO

# Folders
QUEUE_DIR = "queue"
HIGHRES_DIR = "highres_cache"
OUTPUT_DIR = "detections"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Config
VPS_WEBHOOK_URL = "ENTER WEBHOOK URL"
GALLERY_URL = "ENTER WEBPAGE URL"
SPECIES_COOLDOWN = 300.0  
IDLE_TIMEOUT = 300.0      

species_log = {}          
last_activity_time = time.monotonic() 
has_swept_this_idle_period = False   

print("Loading YOLO model...")
model = YOLO("best.pt", task="detect")
print("Ready. Waiting for events...")

while True:
    current_time_mono = time.monotonic()
    
    # --- Garbage Collector ---
    time_since_active = current_time_mono - last_activity_time
    if time_since_active > IDLE_TIMEOUT and not has_swept_this_idle_period:
        print("\n[Sweep] System idle for 5 minutes. Running deep clean...")
        current_wall_time = time.time()
        for directory in [QUEUE_DIR, HIGHRES_DIR]:
            try:
                for f in os.listdir(directory):
                    file_path = os.path.join(directory, f)
                    if current_wall_time - os.path.getmtime(file_path) > 300.0:
                        os.remove(file_path)
            except OSError: pass
        has_swept_this_idle_period = True
        print("[Sweep] Deep clean complete.")

    # --- Processing Loop ---
    try:
        files = os.listdir(QUEUE_DIR)
    except OSError:
        time.sleep(0.5)
        continue

    events = {}
    for f in files:
        if f.startswith("BATCH_") and f.endswith(".jpg"):
            parts = f.split("_")
            if len(parts) >= 3:
                unique_batch_id = f"{parts[1]}_{parts[2]}"
                events.setdefault(unique_batch_id, []).append(f)

    for batch_id, event_files in events.items():
        event_id, slot_id = batch_id.split("_")
        
        # State 1: Incomplete Batch
        if len(event_files) < 5:
            first_file = os.path.join(QUEUE_DIR, sorted(event_files)[0])
            if time.time() - os.path.getmtime(first_file) > 60.0:
                print(f"\n[Purge] Incomplete event {event_id} (Slot {slot_id}) timed out.")
                for f in event_files:
                    try: 
                        os.remove(os.path.join(QUEUE_DIR, f))
                        os.remove(os.path.join(HIGHRES_DIR, f))
                    except OSError: pass
            continue 

        # State 2: Complete Batch
        if len(event_files) >= 5:
            event_files = sorted(event_files)[:5]
            print(f"\n--- Processing Event {event_id} (Slot {slot_id}) ---")
            
            votes = []
            best_result = None
            best_fname = None
            
            for fname in event_files:
                path = os.path.join(QUEUE_DIR, fname)
                t0 = time.perf_counter()
                results = model.predict(source=path, conf=0.15, verbose=False, imgsz=640)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                
                if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                    cls_id = int(results[0].boxes[0].cls[0].item())
                    species = model.names[cls_id].replace(" ", "-")
                    votes.append(species)
                    best_result = results[0]
                    best_fname = fname
                    print(f"  {fname} -> {species} ({elapsed_ms:.1f}ms)")
                else:
                    print(f"  {fname} -> No detection ({elapsed_ms:.1f}ms)")
            
            if votes:
                winner = max(set(votes), key=votes.count)
                if (current_time_mono - species_log.get(winner, 0.0)) >= SPECIES_COOLDOWN:
                    
                    # Correct filename format for VPS parsing
                    save_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{winner}.jpg"
                    save_path = os.path.join(OUTPUT_DIR, save_name)
                    
                    if os.path.exists(os.path.join(HIGHRES_DIR, best_fname)):
                        shutil.copy(os.path.join(HIGHRES_DIR, best_fname), save_path)
                    else:
                        best_result.save(filename=save_path)

                    # Reverted to your original Discord message style
                    msg = f"**New Visitor Alert!** A **{winner.replace('-', ' ')}** has arrived!\n**View Gallery:** {GALLERY_URL}"
                    
                    with open(save_path, "rb") as f:
                        requests.post(VPS_WEBHOOK_URL, 
                                      data={"content": msg}, 
                                      files={"file": (save_name, f, "image/jpeg")})
                    
                    species_log[winner] = current_time_mono
                    print(f"Winner: {winner}. Webhook fired.")
            
            # Cleanup
            for f in event_files:
                try: 
                    os.remove(os.path.join(QUEUE_DIR, f))
                    os.remove(os.path.join(HIGHRES_DIR, f))
                except OSError: pass
            
            last_activity_time = time.monotonic()
            has_swept_this_idle_period = False 

    time.sleep(0.5)
