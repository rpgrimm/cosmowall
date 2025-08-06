#!/usr/bin/env python3

import os
import sys
import json
import pygame
import requests
import textwrap
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
    elif "GNOME" in de:
        print("Gnome detected")
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

def show_with_feh(image_path):
    try:
        subprocess.run(["feh", "--fullscreen", "--auto-zoom", image_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to display image with feh: {e}")

def render_text_with_outline(text, font, text_color, outline_color, outline_width=1):
    base = font.render(text, True, text_color)
    size = (base.get_width() + outline_width * 2, base.get_height() + outline_width * 2)
    outline_surface = pygame.Surface(size, pygame.SRCALPHA)

    # Render outline in 8 directions
    for dx in [-outline_width, 0, outline_width]:
        for dy in [-outline_width, 0, outline_width]:
            if dx != 0 or dy != 0:
                pos = (dx + outline_width, dy + outline_width)
                outline_surface.blit(font.render(text, True, outline_color), pos)

    # Render the main text in the center
    outline_surface.blit(base, (outline_width, outline_width))
    return outline_surface


def view_with_pygame(image_path, title="CosmoWall", explanation=None):

    pygame.init()
    #screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen = pygame.display.set_mode((1400, 1200))  # Windowed mode
    screen_rect = screen.get_rect()
    pygame.display.set_caption("CosmoWall")

    try:
        img = pygame.image.load(image_path)
        img = pygame.transform.scale(img, screen_rect.size)
    except Exception as e:
        print(f"Error loading image in pygame: {e}")
        return

    screen.blit(img, (0, 0))

    # Font setup
    title_font = pygame.font.SysFont("Arial", 42)
    text_font = pygame.font.SysFont("Arial", 28)
    line_height = text_font.get_height() + 6

    # Render title
    #title_surface = title_font.render(title, True, (255, 255, 255))
    title_surface = render_text_with_outline(title, title_font, (255, 255, 255), (0, 0, 0), 1)
    title_rect = title_surface.get_rect(center=(screen_rect.centerx, 60))

    # Render wrapped explanation
    #wrapped_lines = []
    #if explanation:
    #    max_width = screen_rect.width - 100
    #    wrapper = textwrap.TextWrapper(width=90)
    #    lines = wrapper.wrap(explanation)

    #    for line in lines:
    #        surf = text_font.render(line, True, (255, 255, 255))
    #        wrapped_lines.append(surf)

    # Render wrapped explanation
    wrapped_lines = []
    if explanation:
        wrapper = textwrap.TextWrapper(width=90)
        lines = wrapper.wrap(explanation)

        for line in lines:
            #surf = text_font.render(line, True, (255, 255, 255))
            surf = render_text_with_outline(line, text_font, (255, 255, 255), (0, 0, 0), 1)

            rect = surf.get_rect(centerx=screen_rect.centerx)
            wrapped_lines.append((surf, rect))


    # Draw background strip at bottom
    total_text_height = len(wrapped_lines) * line_height + 80
    text_bg = pygame.Surface((screen_rect.width, total_text_height))
    #text_bg.set_alpha(180)
    text_bg.set_alpha(0)
    text_bg.fill((0, 0, 0))
    screen.blit(text_bg, (0, screen_rect.height - total_text_height))

    # Blit title
    screen.blit(title_surface, title_rect)

    # Blit each wrapped line at bottom
    #start_y = screen_rect.height - total_text_height + 60
    #for i, line in enumerate(wrapped_lines):
    #    screen.blit(line, (50, start_y + i * line_height))
    start_y = screen_rect.height - total_text_height + 60
    for i, (surf, rect) in enumerate(wrapped_lines):
        rect.top = start_y + i * line_height
        screen.blit(surf, rect)


    pygame.display.flip()

    # Wait for key or mouse
    running = True
    while running:
        for event in pygame.event.get():
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.QUIT):
                running = False

    pygame.quit()

def view_side_by_side(image_path, title="CosmoWall", explanation=None, fullscreen=False):
    import pygame
    import textwrap

    pygame.init()

    if fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        screen_rect = screen.get_rect()
        screen_width = screen_rect.width
        screen_height = screen_rect.height
    else:
        screen_width = 1900
        screen_height = 1200
        screen = pygame.display.set_mode((screen_width, screen_height))
        screen_rect = screen.get_rect()

    pygame.display.set_caption("CosmoWall: Side by Side")

    screen.fill((0, 0, 0))  # Clear screen

    # Dynamically calculate text area width (e.g. 30% of screen)
    text_area_width = int(screen_width * 0.30)
    image_area_width = screen_width - text_area_width
    image_area = pygame.Rect(text_area_width, 0, image_area_width, screen_height)

    # Load and scale image
    try:
        img = pygame.image.load(image_path)
        img = pygame.transform.scale(img, (image_area.width, image_area.height))
        screen.blit(img, (image_area.left, image_area.top))
    except Exception as e:
        print(f"Failed to load image: {e}")
        return

    # Fonts (adjusted for higher resolution)
    #title_font = pygame.font.SysFont("Arial", 50, bold=True)
    #text_font = pygame.font.SysFont("Arial", 40)
    #line_spacing = 4

    # Fonts (scaled for resolution with higher minimums)
    title_font_size = max(int(screen_height * 0.04), 18)
    text_font_size = max(int(screen_height * 0.02), 16)
    print(title_font_size)
    print(text_font_size)

    title_font = pygame.font.SysFont("Arial", title_font_size, bold=True)
    text_font = pygame.font.SysFont("Arial", text_font_size)
    line_spacing = int(text_font_size * 0.3)  # Spaced nicely


    # Wrap and render all text lines (title + explanation)
    text_surfaces = []

    # Title
    title_surf = title_font.render(title, True, (255, 255, 255))
    title_rect = title_surf.get_rect(centerx=text_area_width // 2)
    text_surfaces.append((title_surf, title_rect))

    # Explanation
    if explanation:
        wrapper = textwrap.TextWrapper(width=40)
        lines = wrapper.wrap(explanation)

        for line in lines:
            surf = text_font.render(line, True, (200, 200, 200))
            rect = surf.get_rect(centerx=text_area_width // 2)
            text_surfaces.append((surf, rect))

    # Vertical centering
    total_text_height = sum(s.get_height() + line_spacing for s, _ in text_surfaces) - line_spacing + 20
    start_y = (screen_height - total_text_height) // 2

    # Blit text surfaces
    for i, (surf, rect) in enumerate(text_surfaces):
        rect.top = start_y
        screen.blit(surf, rect)
        start_y += surf.get_height()

        if i == 0:
            start_y += 20  # Extra space after title
        else:
            start_y += line_spacing

    pygame.display.flip()

    # Wait for quit
    running = True
    while running:
        for event in pygame.event.get():
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.QUIT):
                running = False

    pygame.quit()

def main(date_str=None, set_bg=False, list_cached=False, show_feh=False, show_cosmowall=False, side_by_side=False, fullscreen=False):


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
        if show_feh:
            show_with_feh(image_path)
        if show_cosmowall:
            title = data[date_str]["title"] if date_str in data else apod_data.get("title", "CosmoWall")
            explanation = data[date_str]["explanation"] if date_str in data else apod_data.get("explanation", "CosmoWall Explanation")
            if side_by_side:
                view_side_by_side(image_path, title, explanation, fullscreen)
            else:
                view_with_pygame(image_path, title, explanation)


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

    if show_feh:
        show_with_feh(image_path)

    if show_cosmowall:
        title = data[date_str]["title"] if date_str in data else apod_data.get("title", "CosmoWall")
        explanation = data[date_str]["explanation"] if date_str in data else apod_data.get("explanation", "CosmoWall Explanation")
        if side_by_side:
            view_side_by_side(image_path, title, explanation, fullscreen)
        else:
            view_with_pygame(image_path, title, explanation)

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
    parser.add_argument("--feh", action="store_true", help="Display the APOD image using feh in fullscreen with auto-zoom")
    parser.add_argument("--cosmowall", action="store_true", help="View the APOD image using the CosmoWall pygame viewer")
    parser.add_argument("--side-by-side", action="store_true", help="View APOD image and explanation in side-by-side layout")
    parser.add_argument("--fullscreen", action="store_true", help="Fullscreen mode")

    args = parser.parse_args()

    # Determine date argument
    date_arg = None
    if args.today:
        date_arg = "__TODAY__"
    elif args.date:
        date_arg = args.date

    main(
    date_arg,
    set_bg=args.set_bg,
    list_cached=args.list_cached,
    show_feh=args.feh,
    show_cosmowall=args.cosmowall,
    side_by_side=args.side_by_side,
    fullscreen=args.fullscreen
    )
 
