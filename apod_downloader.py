#!/usr/bin/env python3

import os
import sys
import json
import requests
import subprocess
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse

NASA_API_KEY = os.getenv("NASA_API_KEY")
if not NASA_API_KEY:
    print("NASA_API_KEY environment variable not set.")
    sys.exit(1)

APOD_DIR = Path.home() / "Pictures" / "apod"
APOD_JSON = APOD_DIR / "apod.json"

def fetch_apod_metadata(date_str):
    url = "https://api.nasa.gov/planetary/apod"
    params = {"api_key": NASA_API_KEY, "date": date_str}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def download_image(image_url, save_dir):
    parsed_url = urlparse(image_url)
    filename = os.path.basename(parsed_url.path)
    save_path = save_dir / filename

    response = requests.get(image_url)
    response.raise_for_status()
    with open(save_path, 'wb') as f:
        f.write(response.content)

    return str(save_path)

def load_apod_json():
    if APOD_JSON.exists():
        with open(APOD_JSON, 'r') as f:
            return json.load(f)
    return {}

def save_apod_json(data):
    APOD_DIR.mkdir(parents=True, exist_ok=True)
    with open(APOD_JSON, 'w') as f:
        json.dump(data, f, indent=2)

def update_apod_json(date_str, meta, image_path):
    data = load_apod_json()
    data[date_str] = {
        "title": meta.get("title", ""),
        "explanation": meta.get("explanation", ""),
        "url": meta.get("url", ""),
        "img": image_path
    }
    save_apod_json(data)

def get_desktop_env():

    if "XDG_CURRENT_DESKTOP" in os.environ:
        if os.environ['XDG_CURRENT_DESKTOP'] == 'ubuntu:GNOME':
            return 'ubuntu:GNOME'

    try:
        output = subprocess.check_output(["pgrep", "-l", "xfce4-session"])
        return 'ubuntu:xfce4'
    except subprocess.CalledProcessError:
        print("subprocess pgrep xfce4-session failed")

def set_background(image_path):
    de = get_desktop_env()
    if "xfce" in de:
        set_xfce_background(image_path)
    elif "gnome" in de:
        set_gnome_background(image_path)
    #else:
    #    set_feh_background(image_path)  # fallback

def set_gnome_background(image_path):
    uri = f"file://{image_path}"
    cmds = [
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
        ["gsettings", "set", "org.gnome.desktop.background", "picture-options", "scaled"],
        ["gsettings", "set", "org.gnome.desktop.background", "primary-color", "#000000"],
        ["gsettings", "set", "org.gnome.desktop.background", "color-shading-type", "solid"],
    ]
    for cmd in cmds:
        subprocess.run(cmd, check=True)
    print(f"Set desktop background to {image_path}")

#/backdrop/screen0/monitor0/workspace0/last-image
def set_xfce_background(wallpaper_path):
    # Ensure the wallpaper path is absolute
    wallpaper_path = os.path.abspath(os.path.expanduser(wallpaper_path))

    try:
        # Get all xfce4-desktop properties
        output = subprocess.check_output(
            ["xfconf-query", "-c", "xfce4-desktop", "-l"],
            universal_newlines=True
        )
        # Filter for 'last-image' properties
        props = [line for line in output.strip().split('\n') if 'last-image' in line]

        # Set wallpaper for each last-image property
        for prop in props:
            subprocess.run([
                "xfconf-query", "-c", "xfce4-desktop",
                "-p", prop,
                "-s", wallpaper_path
            ], check=True)

        # Reload desktop
	# Don't seem to need this
        #subprocess.run(["xfdesktop", "--reload"], check=True)

        print("Wallpaper set successfully.")

    except subprocess.CalledProcessError as e:
        print("Error:", e)


def is_valid_date(date_str):
    try:
        # Try to create a datetime object with the given format
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError as e:
        # If a ValueError is raised, the format is incorrect
        print(f"Invalid date format: {e}")
        return False

def list_cached_apods():
    data = load_apod_json()
    if not data:
        print("No cached APODs found.")
        return

    for date_str, entry in sorted(data.items()):
        title = entry.get("title", "No Title")
        explanation = entry.get("explanation", "No explanation")
        print(f"🗓️ {date_str}: {title}\n   {explanation[:200]}...\n")



def main(date_str=None, set_bg=False, list_cached=False):

    # Handle --today
    if date_str == "__TODAY__":
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if list_cached:
        list_cached_apods()
        return

    if not date_str:
        print("Date is required unless --list-cached is used.")
        sys.exit(1)

    if not is_valid_date(date_str):
        print(f'error invalid date string {date_str}')
        sys.exit(1)

    data = load_apod_json()

    # If image already exists in JSON, use it
    if date_str in data:
        image_path = data[date_str]["img"]
        if set_bg:
            set_background(image_path)
        print(f"Using cached APOD for {date_str} -> {image_path}\n")
        print(f"Title: {data[date_str].get('title', '')}\n")
        print(f"Explanation: {data[date_str].get('explanation', '')}")
        return

    # Otherwise, fetch and store new image
    base_dir = APOD_DIR / date_str
    base_dir.mkdir(parents=True, exist_ok=True)

    apod_data = fetch_apod_metadata(date_str)
    media_type = apod_data.get("media_type")

    if media_type != "image":
        print(f"{date_str} is not an image (media_type={media_type}). Skipping download.")
        print(f"{apod_data.get('Title')} .")
        return

    image_url = apod_data.get("hdurl") or apod_data.get("url")
    if not image_url:
        print(f"No image URL found for {date_str}")
        return

    image_path = download_image(image_url, base_dir)
    update_apod_json(date_str, apod_data, image_path)

    if set_bg:
        set_background(image_path)

    print(f"Saved APOD {date_str} -> {image_path}")
    print(f"Title: {apod_data.get('title', '')}\n")
    print(f"Explanation: {apod_data.get('explanation', '')}\n")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("date", nargs="?", help="Date in ISO 8601 YYYY-MM-DD format (use 'TODAY' to fetch today's APOD)")
    parser.add_argument("--set-bg", action="store_true", help="Set the APOD image as GNOME background")
    parser.add_argument("--list-cached", action="store_true", help="List cached APOD images")
    parser.add_argument("--today", action="store_true", help="Shortcut for today's date")
    args = parser.parse_args()

    # Determine date argument
    date_arg = None
    if args.today:
        date_arg = "__TODAY__"
    elif args.date:
        date_arg = args.date

    main(date_arg, set_bg=args.set_bg, list_cached=args.list_cached)
