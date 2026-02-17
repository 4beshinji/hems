# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "opencv-python-headless",
#     "ultralytics",
#     "rich",
#     "httpx",
#     "numpy",
#     "torch",
#     "torchvision",
# ]
# [tool.uv]
# extra-index-url = ["https://download.pytorch.org/whl/rocm6.2"]
# ///

import cv2
import httpx
import re
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from ultralytics import YOLO
import logging

# Suppress YOLO logging
logging.getLogger("ultralytics").setLevel(logging.ERROR)
import torch

SCAN_FILE = "scan_final.txt"
TIMEOUT = 3.0

console = Console(width=200)

def extract_ips(filename):
    ips = []
    try:
        with open(filename, 'r') as f:
            content = f.read()
            # Look for lines starting with │ <ip>
            matches = re.finditer(r'│\s+(\d+\.\d+\.\d+\.\d+)\s+│', content)
            for match in matches:
                ip = match.group(1)
                if ip not in ips:
                    ips.append(ip)
    except FileNotFoundError:
        console.print(f"[red]Error: {filename} not found.[/red]")
    return ips

def check_stream(ip, model):
    # Common stream URLs
    # ESP32-CAM often uses :81/stream
    # OctoPrint often uses :8080/?action=stream or /webcam/?action=stream
    candidate_urls = [
        f"http://{ip}:81/",
        f"http://{ip}:81/stream",
        f"http://{ip}/stream",
        f"http://{ip}:8080/?action=stream",
        f"http://{ip}/webcam/?action=stream",
        f"http://{ip}:8000/stream.mjpg",
    ]

    for url in candidate_urls:
        try:
            # Quick check with cv2
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                continue
            
            ret, frame = cap.read()
            if ret and frame is not None:
                # We have a stream!
                # Run YOLO
                results = model(frame, verbose=False)
                detections = []
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        if conf > 0.4:
                            name = model.names[cls_id]
                            detections.append(f"{name} ({conf:.2f})")
                
                cap.release()
                return url, detections, len(detections) > 0
            
            cap.release()
        except Exception:
            continue
            
    return None, [], False

def main():
    console.print(f"[bold blue]Torch Version: {torch.__version__}[/bold blue]")
    console.print(f"[bold blue]ROCm (HIP) available: {torch.version.hip}[/bold blue]")
    console.print(f"[bold blue]CUDA available: {torch.cuda.is_available()}[/bold blue]")
    if torch.cuda.is_available():
         console.print(f"[green]Using GPU: {torch.cuda.get_device_name(0)}[/green]")
    else:
         console.print(f"[yellow]Using CPU[/yellow]")

    console.print(f"[bold blue]Loading YOLOv8n model...[/bold blue]")
    try:
        model = YOLO("yolov8n.pt")
    except Exception as e:
        console.print(f"[red]Failed to load YOLO model: {e}[/red]")
        return

    console.print(f"[bold blue]Extracting IPs from {SCAN_FILE}...[/bold blue]")
    ips = extract_ips(SCAN_FILE)
    console.print(f"[cyan]Found {len(ips)} distinct IPs.[/cyan]")

    table = Table(title="Camera Verification Results")
    table.add_column("IP Address", style="cyan")
    table.add_column("Stream OK?", style="blue")
    table.add_column("Object Detected?", style="magenta")
    table.add_column("Stream URL", style="green")
    table.add_column("Detections", style="yellow")

    active_cameras = 0

    with Progress() as progress:
        task = progress.add_task("[cyan]Verifying cameras...", total=len(ips))
        
        for ip in ips:
            url, detections, has_objects = check_stream(ip, model)
            
            if url:
                stream_status = "[bold green]YES[/bold green]"
                if has_objects:
                    obj_status = "[bold green]YES[/bold green]"
                    det_str = ", ".join(detections)
                    active_cameras += 1
                else:
                    obj_status = "[red]NO[/red]"
                    det_str = "None"
                
                table.add_row(ip, stream_status, obj_status, url, det_str)
            else:
                 # Optional: Log failed IPs if needed, but keeping it clean for now
                 pass
            
            progress.update(task, advance=1)

    console.print(table)
    console.print(f"\n[bold green]Total Active Cameras Found: {active_cameras}[/bold green]")

    # Also detecting 3D printers that might have auth but are "alive" as services
    # The previous scan identified them. This script focuses on VIDEO STREAMS.

if __name__ == "__main__":
    main()
