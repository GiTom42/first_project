__author__ = "__Tom Wallerstein__"

import pygame
import math
import sys

# ====================== CONSTANTS ======================
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

# === CIRCULAR MAP ===
MAP_RADIUS = 650                    # Big enough circular world
MAP_CENTER_X = MAP_RADIUS
MAP_CENTER_Y = MAP_RADIUS
MAP_WIDTH = MAP_RADIUS * 2          # Full surface size
MAP_HEIGHT = MAP_RADIUS * 2

PLAYER_WIDTH = 35
PLAYER_HEIGHT = 35
PLAYER_SPEED = 3

PLAYER_SCREEN_X = WINDOW_WIDTH // 2 - PLAYER_WIDTH // 2
PLAYER_SCREEN_Y = WINDOW_HEIGHT // 2 - PLAYER_HEIGHT // 2

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
PLAYER_COLOR = (0, 0, 255)
TRAIL_COLOR = (100, 149, 237)
PUDDLE_COLOR = (0, 80, 170)

TRAIL_WIDTH = PLAYER_WIDTH

# Initial Circular Puddle
PUDDLE_CENTER_X = MAP_CENTER_X
PUDDLE_CENTER_Y = MAP_CENTER_Y
PUDDLE_RADIUS = 90

# ====================== HELPER FUNCTIONS ======================
def point_to_segment_dist(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0, min(1, t))

    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.hypot(px - closest_x, py - closest_y)


# ====================== SETUP ======================
pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Paper.io - Circular Map")

# Main map surface (now bigger to fit circle)
map_surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
map_surface.fill(BLACK)  # Black = outside the round world

# Create circular playable area
pygame.draw.circle(map_surface, WHITE, (MAP_CENTER_X, MAP_CENTER_Y), MAP_RADIUS)

puddle_surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
puddle_surface.fill((0, 0, 0, 0))
pygame.draw.circle(puddle_surface, PUDDLE_COLOR, (PUDDLE_CENTER_X, PUDDLE_CENTER_Y), PUDDLE_RADIUS)

player_original = pygame.Surface((PLAYER_WIDTH, PLAYER_HEIGHT), pygame.SRCALPHA)
player_original.fill(PLAYER_COLOR)

# Start in center
player_map_x = MAP_CENTER_X - PLAYER_WIDTH / 2.0
player_map_y = MAP_CENTER_Y - PLAYER_HEIGHT / 2.0

clock = pygame.time.Clock()

was_inside_puddle = True
last_inside_pos = (player_map_x + PLAYER_WIDTH / 2, player_map_y + PLAYER_HEIGHT / 2)
trail_points = []

font = pygame.font.Font(None, 74)

# Edge mask for claiming (still useful)
edge_mask = pygame.mask.Mask((MAP_WIDTH, MAP_HEIGHT))
edge_mask.fill()
inner_mask = pygame.mask.Mask((MAP_WIDTH - 2, MAP_HEIGHT - 2))
inner_mask.fill()
edge_mask.erase(inner_mask, (1, 1))

# ====================== MAIN LOOP ======================
running = True
game_over = False

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    if game_over:
        screen.fill(BLACK)
        text = font.render("GAME OVER", True, (255, 0, 0))
        screen.blit(text, (WINDOW_WIDTH // 2 - text.get_width() // 2, WINDOW_HEIGHT // 2 - 50))
        pygame.display.flip()
        clock.tick(60)
        continue

    # Camera
    cam_x = int(player_map_x + PLAYER_WIDTH / 2 - WINDOW_WIDTH / 2)
    cam_y = int(player_map_y + PLAYER_HEIGHT / 2 - WINDOW_HEIGHT / 2)

    # Mouse map position
    mouse_screen_x, mouse_screen_y = pygame.mouse.get_pos()
    mouse_map_x = cam_x + mouse_screen_x
    mouse_map_y = cam_y + mouse_screen_y

    # Movement Logic + Circular Boundary
    dx = mouse_map_x - (player_map_x + PLAYER_WIDTH / 2)
    dy = mouse_map_y - (player_map_y + PLAYER_HEIGHT / 2)
    distance = math.hypot(dx, dy)

    if distance > 0:
        move_x = (dx / distance) * PLAYER_SPEED
        move_y = (dy / distance) * PLAYER_SPEED

        player_map_x += move_x
        player_map_y += move_y

        # === CIRCULAR BOUNDARY ===
        center_x = player_map_x + PLAYER_WIDTH / 2
        center_y = player_map_y + PLAYER_HEIGHT / 2
        dist_from_center = math.hypot(center_x - MAP_CENTER_X, center_y - MAP_CENTER_Y)

        if dist_from_center > MAP_RADIUS - PLAYER_WIDTH / 2:
            angle = math.atan2(center_y - MAP_CENTER_Y, center_x - MAP_CENTER_X)
            player_map_x = MAP_CENTER_X - PLAYER_WIDTH / 2 + math.cos(angle) * (MAP_RADIUS - PLAYER_WIDTH / 2)
            player_map_y = MAP_CENTER_Y - PLAYER_HEIGHT / 2 + math.sin(angle) * (MAP_RADIUS - PLAYER_HEIGHT / 2)

    player_center = (player_map_x + PLAYER_WIDTH / 2, player_map_y + PLAYER_HEIGHT / 2)

    # Puddle check
    px, py = int(player_center[0]), int(player_center[1])
    is_inside_puddle = (0 <= px < MAP_WIDTH and 0 <= py < MAP_HEIGHT and
                        puddle_surface.get_at((px, py))[3] > 0)

    # Trail Tracking Logic (unchanged)
    if is_inside_puddle:
        last_inside_pos = player_center
    else:
        if was_inside_puddle:
            trail_points.append(last_inside_pos)
        if not trail_points or math.hypot(trail_points[-1][0] - player_center[0],
                                          trail_points[-1][1] - player_center[1]) > 3:
            trail_points.append(player_center)

    # === AREA CLAIMING (unchanged) ===
    if is_inside_puddle and not was_inside_puddle:
        trail_points.append(player_center)
        if len(trail_points) >= 2:
            temp_surf = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
            for i in range(len(trail_points) - 1):
                pygame.draw.line(temp_surf, PUDDLE_COLOR, trail_points[i], trail_points[i + 1], TRAIL_WIDTH + 2)
                pygame.draw.circle(temp_surf, PUDDLE_COLOR, trail_points[i], (TRAIL_WIDTH // 2) + 1)
            pygame.draw.circle(temp_surf, PUDDLE_COLOR, trail_points[-1], (TRAIL_WIDTH // 2) + 1)

            puddle_surface.blit(temp_surf, (0, 0))

            solid_mask = pygame.mask.from_surface(puddle_surface)
            empty_mask = solid_mask.copy()
            empty_mask.invert()

            components = empty_mask.connected_components()
            enclosed_mask = pygame.mask.Mask((MAP_WIDTH, MAP_HEIGHT))

            for comp in components:
                if not comp.overlap(edge_mask, (0, 0)):
                    enclosed_mask.draw(comp, (0, 0))

            if enclosed_mask.count() > 0:
                enclosed_surf = enclosed_mask.to_surface(setcolor=(*PUDDLE_COLOR, 255), unsetcolor=(0, 0, 0, 0))
                puddle_surface.blit(enclosed_surf, (0, 0))

        trail_points = []

    # === DEATH CHECK (unchanged) ===
    if not is_inside_puddle and len(trail_points) >= 2:
        hitbox_radius = PLAYER_WIDTH / 2 - 2
        path_dist = 0
        safe_index = len(trail_points) - 1

        while safe_index > 0:
            p1 = trail_points[safe_index]
            p2 = trail_points[safe_index - 1]
            path_dist += math.hypot(p1[0] - p2[0], p1[1] - p2[1])
            safe_index -= 1
            if path_dist > PLAYER_WIDTH * 2:
                break

        for i in range(safe_index):
            dist = point_to_segment_dist(player_center, trail_points[i], trail_points[i + 1])
            if dist < hitbox_radius + (TRAIL_WIDTH / 2):
                game_over = True
                break

    was_inside_puddle = is_inside_puddle

    # Rotation
    at_border = False  # Not used for circular map

    if distance > 0:
        angle_degrees = math.degrees(math.atan2(dy, dx))
    else:
        angle_degrees = 0

    rotated_surface = pygame.transform.rotate(player_original, -angle_degrees)
    rotated_rect = rotated_surface.get_rect(
        center=(PLAYER_SCREEN_X + PLAYER_WIDTH // 2, PLAYER_SCREEN_Y + PLAYER_HEIGHT // 2)
    )

    # === DRAWING ===
    screen.fill(BLACK)

    # Draw map (circular world)
    screen.blit(map_surface, (-cam_x, -cam_y))

    # Draw active trail
    if len(trail_points) >= 2:
        for i in range(len(trail_points) - 1):
            start = (trail_points[i][0] - cam_x, trail_points[i][1] - cam_y)
            end = (trail_points[i + 1][0] - cam_x, trail_points[i + 1][1] - cam_y)
            pygame.draw.line(screen, TRAIL_COLOR, start, end, TRAIL_WIDTH)
            pygame.draw.circle(screen, TRAIL_COLOR, start, TRAIL_WIDTH // 2)
        last_pt = (trail_points[-1][0] - cam_x, trail_points[-1][1] - cam_y)
        pygame.draw.circle(screen, TRAIL_COLOR, last_pt, TRAIL_WIDTH // 2)

    # Draw puddle on top
    screen.blit(puddle_surface, (-cam_x, -cam_y))

    # Player
    screen.blit(rotated_surface, rotated_rect)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()