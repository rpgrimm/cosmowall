#!/usr/bin/env python3

import os
import sys
import json
import pygame
import requests
import textwrap
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime,timezone

from narratron import Narratron

NASA_API_KEY = os.getenv("NASA_API_KEY")
if not NASA_API_KEY:
    print("NASA_API_KEY environment variable not set.")
    sys.exit(1)

APOD_DIR = Path.home() / "Pictures" / "apod"
APOD_JSON = APOD_DIR / "apod.json"

def sanitize_stem(name: str) -> str:
    # keeps it filesystem-friendly
    stem = Path(name).stem
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in stem)
    return safe or "apod"

def build_mp3_path_for_image(image_path: str) -> Path:
    p = Path(image_path)
    return p.with_suffix(".mp3")

def ensure_apod_audio(date_str: str, entry: dict, voice_id: str, force: bool = False) -> Path:
    """
    Create (or reuse) an MP3 for this APOD, store path under entry['mp3'], and persist JSON.
    Uses Narratron.voice_process_text_input(text, voice_id, output=<mp3 path>).
    """
    image_path = entry.get("img")
    if not image_path:
        raise RuntimeError(f"No image path for {date_str}; cannot create audio.")

    mp3_path = build_mp3_path_for_image(image_path)

    if mp3_path.exists() and not force:
        # already cached; make sure JSON points to it
        if entry.get("mp3") != str(mp3_path):
            data = load_apod_json()
            data[date_str]["mp3"] = str(mp3_path)
            save_apod_json(data)
        return mp3_path

    # Build text: title + explanation
    title = entry.get("title", "").strip()
    explanation = entry.get("explanation", "").strip()
    text = f"{title}\n\n{explanation}".strip() or "Astronomy Picture of the Day."

    # Make sure the directory exists
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    # Call Narratron
    nar = Narratron()
    print(f"Generating {mp3_path}")
    nar.voice_process_text_input(text=text, voice_id=voice_id, output=str(mp3_path))

    # Update JSON
    data = load_apod_json()
    if date_str not in data:
        data[date_str] = {}
    data[date_str]["mp3"] = str(mp3_path)
    save_apod_json(data)

    return mp3_path


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
    return data

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
    pygame.mouse.set_visible(False)

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

def view_cosmowall_layout(apod_data_dict, start_date, fullscreen=False):
    import pygame
    import textwrap
    from datetime import datetime

    def render_apod(screen, screen_width, screen_height, title_height, text_width,
                    image_path, title, explanation):
        screen.fill((0, 0, 0))

        # Fonts (scaled)
        title_font_size = max(int(screen_height * 0.04), 36)

        #print("len explanation: %d" % len(explanation))
        screen_height_multiplier = .03
        if len(explanation) > 800:
            screen_height_multiplier = .02
        text_font_size = max(int(screen_height * screen_height_multiplier), 26)
        title_font = pygame.font.SysFont("Arial", title_font_size, bold=True)
        text_font = pygame.font.SysFont("Arial", text_font_size)
        line_spacing = int(text_font_size * 0.3)

        # --- Title bar ---
        title_rect = pygame.Rect(0, 0, screen_width, title_height)
        pygame.draw.rect(screen, (0, 0, 0), title_rect)
        title_surf = title_font.render(title, True, (255, 255, 255))
        title_surf_rect = title_surf.get_rect(center=(screen_width // 2, title_height // 2))
        screen.blit(title_surf, title_surf_rect)

        # --- Explanation column ---
        explanation_area = pygame.Rect(0, title_height, text_width, screen_height - title_height)
        pygame.draw.rect(screen, (0, 0, 0), explanation_area)

        # Wrap and render text
        text_surfaces = []
        wrapper = textwrap.TextWrapper(width=40)
        lines = wrapper.wrap(explanation)

        for line in lines:
            surf = text_font.render(line, True, (200, 200, 200))
            rect = surf.get_rect(centerx=explanation_area.width // 2)
            text_surfaces.append((surf, rect))

        total_text_height = sum(s.get_height() + line_spacing for s, _ in text_surfaces) - line_spacing
        start_y = explanation_area.top + (explanation_area.height - total_text_height) // 2

        for surf, rect in text_surfaces:
            rect.top = start_y
            screen.blit(surf, rect)
            start_y += surf.get_height() + line_spacing

        # --- Image area ---
        image_area = pygame.Rect(text_width, title_height,
                                 screen_width - text_width, screen_height - title_height)

        try:
            img = pygame.image.load(image_path)
            img = pygame.transform.scale(img, (image_area.width, image_area.height))
            screen.blit(img, (image_area.left, image_area.top))
        except Exception as e:
            print(f"Failed to load image: {e}")

        pygame.display.flip()

    # Init
    pygame.init()
    pygame.mouse.set_visible(False)

    if fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode((1900, 1200))

    screen_rect = screen.get_rect()
    screen_width, screen_height = screen_rect.width, screen_rect.height

    # Layout constants (percentages of screen)
    title_height = int(screen_height * 0.12)
    text_width = int(screen_width * 0.33)

    # Sort cached APODs
    date_list = sorted(apod_data_dict.keys(), key=lambda d: datetime.strptime(d, "%Y-%m-%d"))
    current_index = date_list.index(start_date) if start_date in date_list else 0

    running = True
    while running:
        date_str = date_list[current_index]
        entry = apod_data_dict[date_str]
        image_path = entry["img"]
        title = entry.get("title", "")
        explanation = entry.get("explanation", "")

        render_apod(screen, screen_width, screen_height, title_height, text_width,
                    image_path, title, explanation)

        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.KEYDOWN):
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click → next image
                    current_index = (current_index + 1) % len(date_list)
                elif event.button == 3:  # Right click → previous
                    current_index = (current_index - 1) % len(date_list)
                elif event.button == 2:  # Middle click → play audio
                    entry = apod_data_dict[date_str]
                    mp3_path = entry.get("mp3")
                    if mp3_path and Path(mp3_path).exists():
                        play_audio_nonblocking(mp3_path)
                    else:
                        print("No audio file found for this APOD")

    pygame.quit()


def view_side_by_side_loop(apod_data_dict, start_date, fullscreen=False):
    import pygame
    import textwrap
    from datetime import datetime

    def render_apod(screen, screen_width, screen_height, text_area_width, image_path, title, explanation):
        screen.fill((0, 0, 0))

        # Load and scale image
        image_area_width = screen_width - text_area_width
        image_area = pygame.Rect(text_area_width, 0, image_area_width, screen_height)

        try:
            img = pygame.image.load(image_path)
            img = pygame.transform.scale(img, (image_area.width, image_area.height))
            screen.blit(img, (image_area.left, image_area.top))
        except Exception as e:
            print(f"Failed to load image: {e}")
            return

        # Fonts (scaled)
        title_font_size = max(int(screen_height * 0.04), 32)
        text_font_size = max(int(screen_height * 0.02), 26)
        title_font = pygame.font.SysFont("Arial", title_font_size, bold=True)
        text_font = pygame.font.SysFont("Arial", text_font_size)
        line_spacing = int(text_font_size * 0.3)

        # Wrap and render text
        text_surfaces = []

        # Title
        title_surf = title_font.render(title, True, (255, 255, 255))
        title_rect = title_surf.get_rect(centerx=text_area_width // 2)
        text_surfaces.append((title_surf, title_rect))

        # Explanation
        wrapper = textwrap.TextWrapper(width=40)
        lines = wrapper.wrap(explanation)
        for line in lines:
            surf = text_font.render(line, True, (200, 200, 200))
            rect = surf.get_rect(centerx=text_area_width // 2)
            text_surfaces.append((surf, rect))

        # Vertical centering
        total_text_height = sum(s.get_height() + line_spacing for s, _ in text_surfaces) - line_spacing + 20
        start_y = (screen_height - total_text_height) // 2

        # Blit text
        for i, (surf, rect) in enumerate(text_surfaces):
            rect.top = start_y
            screen.blit(surf, rect)
            start_y += surf.get_height()
            start_y += 20 if i == 0 else line_spacing

        pygame.display.flip()

    # Init pygame
    pygame.init()
    pygame.mouse.set_visible(False)

    if fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        screen_rect = screen.get_rect()
    else:
        screen = pygame.display.set_mode((1900, 1200))
        screen_rect = screen.get_rect()

    screen_width, screen_height = screen_rect.width, screen_rect.height
    text_area_width = int(screen_width * 0.30)

    # Sort dates
    date_list = sorted(apod_data_dict.keys(), key=lambda d: datetime.strptime(d, "%Y-%m-%d"))
    current_index = date_list.index(start_date) if start_date in date_list else 0

    running = True
    while running:
        date_str = date_list[current_index]
        entry = apod_data_dict[date_str]
        image_path = entry["img"]
        title = entry.get("title", "")
        explanation = entry.get("explanation", "")

        render_apod(screen, screen_width, screen_height, text_area_width, image_path, title, explanation)

        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click → next
                    current_index = (current_index + 1) % len(date_list)
                elif event.button == 3:  # Right click → previous
                    current_index = (current_index - 1) % len(date_list)

    pygame.quit()


def view_side_by_side(image_path, title="CosmoWall", explanation=None, fullscreen=False):
    import pygame
    import textwrap

    pygame.init()
    pygame.mouse.set_visible(False)

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
    #print(title_font_size)
    #print(text_font_size)

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

def play_audio_nonblocking(mp3_path):
    """
    Launch cvlc in the background so it plays once and exits,
    without blocking the main pygame loop.
    """
    try:
        subprocess.Popen(
            ["cvlc", "--play-and-exit", mp3_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"Playing audio in background: {mp3_path}")
    except Exception as e:
        print(f"Failed to play audio: {e}")


def main(date_str=None, set_bg=False, list_cached=False, show_feh=False, show_cosmowall=False, side_by_side=False, fullscreen=False, loop=False,
             make_audio=False, force_audio=False, voice_id="vGXjfeBcfruJsIPYQicx", play_audio=False):

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
    if not date_str in data:

        print(f"{date_str} not in cache, fetching from APOD")  
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
        data = update_apod_json(date_str, apod_data, image_path)

        print(f"Saved APOD {date_str} -> {image_path}")
        print(f"Title: {apod_data.get('title', '')}\n")
        print(f"Explanation: {apod_data.get('explanation', '')}\n")

    image_path = data[date_str]["img"]
    # At this point, data[date_str] exists
    if make_audio:
        try:
            mp3_path = ensure_apod_audio(
                date_str=date_str,
                entry=data[date_str],
                voice_id=voice_id,
                force=force_audio
            )
            print(f"Audio cached: {mp3_path}")
        except Exception as e:
            print(f"Failed to generate audio: {e}")

    if play_audio:
        mp3_path = data[date_str].get("mp3")
        if not mp3_path or not Path(mp3_path).exists():
            print("No cached audio found — generating...")
            mp3_path = ensure_apod_audio(
                date_str=date_str,
                entry=data[date_str],
                voice_id=voice_id,
                force=False
            )
        play_audio_nonblocking(mp3_path)

    if set_bg:
        set_background(image_path)
    if show_feh:
        show_with_feh(image_path)
    if show_cosmowall:
        if loop:
            #view_side_by_side_loop(data, date_str, fullscreen)
            view_cosmowall_layout(
                apod_data_dict=data,
                start_date=date_str,
                fullscreen=fullscreen
            )


        title = data[date_str]["title"] if date_str in data else apod_data.get("title", "CosmoWall")
        explanation = data[date_str]["explanation"] if date_str in data else apod_data.get("explanation", "CosmoWall Explanation")
        if side_by_side:
            view_side_by_side(image_path, title, explanation, fullscreen)
        else:
            view_with_pygame(image_path, title, explanation)

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
    parser.add_argument("--loop", action="store_true", help="Loop mode")
    parser.add_argument("--make-audio", action="store_true", help="Generate mp3 for the APOD and cache it")
    parser.add_argument("--force-audio", action="store_true", help="Overwrite an existing mp3 cache for this APOD")
    parser.add_argument("--voice-id", default="vGXjfeBcfruJsIPYQicx", help="Narratron/ElevenLabs voice_id to use")
    parser.add_argument("--play-audio", action="store_true", help="Play the APOD mp3 once using cvlc")

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
        fullscreen=args.fullscreen,
        loop=args.loop,
        make_audio=args.make_audio,
        force_audio=args.force_audio,
        voice_id=args.voice_id,
        play_audio=args.play_audio,
    )

