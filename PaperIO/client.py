__author__ = "__Tom Wallerstein__"

from typing import Mapping

# ======================= IMPORTS =======================
import pygame
import math

# ====================== CONSTANTS ======================
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

# The REAL map size
MAP_WIDTH = 800
MAP_HEIGHT = 600

PLAYER_WIDTH = 35
PLAYER_HEIGHT = 35
PLAYER_SPEED = 5
PLAYER_SCREEN_X = WINDOW_WIDTH // 2 - PLAYER_WIDTH // 2
PLAYER_SCREEN_Y = WINDOW_HEIGHT // 2 - PLAYER_HEIGHT // 2

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)

# ====================== SETUP ======================
pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Paper.io")

# The big map surface
map_surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
map_surface.fill(WHITE)

# === Create the original (unrotated) player as a Surface ===
player_original = pygame.Surface((PLAYER_WIDTH, PLAYER_HEIGHT), pygame.SRCALPHA)
player_original.fill(BLUE)

# Player position is tracked in world coordinates (float = smooth movement)
player_map_x = (MAP_WIDTH - PLAYER_WIDTH) / 2
player_map_y = (MAP_HEIGHT - PLAYER_HEIGHT) / 2

clock = pygame.time.Clock()

# ====================== MAIN LOOP ======================
running = True
while running:
    # --- Event handling ---
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # --- Camera (centered on player) ---
    screen_x = int(player_map_x + PLAYER_WIDTH / 2 - WINDOW_WIDTH / 2)
    screen_y = int(player_map_y + PLAYER_HEIGHT / 2 - WINDOW_HEIGHT / 2)

    # --- Convert mouse position from screen → world coordinates ---
    mouse_screen_x, mouse_screen_y = pygame.mouse.get_pos()
    mouse_map_x = screen_x + mouse_screen_x
    mouse_map_y = screen_y + mouse_screen_y

    # --- Movement (smooth toward mouse) ---
    dx = mouse_map_x - (player_map_x + PLAYER_WIDTH / 2)
    dy = mouse_map_y - (player_map_y + PLAYER_HEIGHT / 2)
    distance = math.hypot(dx, dy)

    if distance > 0:
        move_x = (dx / distance) * PLAYER_SPEED
        move_y = (dy / distance) * PLAYER_SPEED

        player_map_x += move_x
        player_map_y += move_y

        # Keep player inside the world
        player_map_x = max(0, min(player_map_x, MAP_WIDTH - PLAYER_WIDTH))
        player_map_y = max(0, min(player_map_y, MAP_HEIGHT - PLAYER_HEIGHT))

    # === Calculate rotation angle so one side always follows the mouse ===
    at_border = (player_map_x <= 0 or player_map_x >= MAP_WIDTH - PLAYER_WIDTH or
                 player_map_y <= 0 or player_map_y >= MAP_HEIGHT - PLAYER_HEIGHT)

    if distance > 0 and not at_border:
        angle_radians = math.atan2(dy, dx)
        angle_degrees = math.degrees(angle_radians)
    else:
        angle_degrees = 0  # mouse exactly on center → no rotation change

    # Rotate a
    # fresh copy of the original player surface
    rotated_surface = pygame.transform.rotate(player_original, -angle_degrees)

    # Get the rectangle of the rotated surface and center it on the screen
    # (this keeps the player perfectly fixed in the middle even after rotation)
    rotated_rect = rotated_surface.get_rect(
        center=(PLAYER_SCREEN_X + PLAYER_WIDTH // 2,
                PLAYER_SCREEN_Y + PLAYER_HEIGHT // 2)
    )

    # --- Drawing ---
    screen.fill(BLACK)

    # Calculate the visible portion of the map
    map_left = max(0, screen_x)
    map_top = max(0, screen_y)
    map_right = min(MAP_WIDTH, screen_x + WINDOW_WIDTH)
    map_bottom = min(MAP_HEIGHT, screen_y + WINDOW_HEIGHT)

    visible_width = map_right - map_left
    visible_height = map_bottom - map_top

    if visible_width > 0 and visible_height > 0:
        source_rect = pygame.Rect(map_left, map_top, visible_width, visible_height)
        dest_x = max(0, -screen_x)
        dest_y = max(0, -screen_y)
        screen.blit(map_surface, (dest_x, dest_y), source_rect)

    # === Draw the rotated player instead of the old rect ===
    screen.blit(rotated_surface, rotated_rect)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
#Note