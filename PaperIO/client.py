from tcp_by_size import send_with_size, recv_by_size
import socket
import sys
import math
import pygame

# ====================== CONSTANTS ======================
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

MAP_RADIUS = 650
MAP_CENTER_X = MAP_RADIUS
MAP_CENTER_Y = MAP_RADIUS
MAP_WIDTH = MAP_RADIUS * 2
MAP_HEIGHT = MAP_RADIUS * 2

PLAYER_WIDTH = 35
PLAYER_HEIGHT = 35
PLAYER_SCREEN_X = WINDOW_WIDTH // 2 - PLAYER_WIDTH // 2
PLAYER_SCREEN_Y = WINDOW_HEIGHT // 2 - PLAYER_HEIGHT // 2

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
TRAIL_ALPHA_COLOR = (100, 149, 237)
PUDDLE_BASE_COLOR = (0, 80, 170)
TRAIL_WIDTH = PLAYER_WIDTH
PUDDLE_RADIUS = 90

pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Paper.io Multiplayer")
clock = pygame.time.Clock()

font = pygame.font.Font(None, 74)
button_font = pygame.font.Font(None, 40)
start_button_rect = pygame.Rect(WINDOW_WIDTH // 2 - 125, WINDOW_HEIGHT // 2 - 35, 250, 70)

puddle_surfaces = {}


def create_local_puddle(color, start_x, start_y):
    surf = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    pygame.draw.circle(surf, (max(0, color[0] - 40), max(0, color[1] - 40), max(0, color[2] - 40), 255),
                       (start_x, start_y), PUDDLE_RADIUS)
    return surf


def draw_local_capture(surf, points, color):
    if len(points) < 2: return
    p_color = (max(0, color[0] - 40), max(0, color[1] - 40), max(0, color[2] - 40), 255)

    temp_surf = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
    for i in range(len(points) - 1):
        pygame.draw.line(temp_surf, p_color, points[i], points[i + 1], TRAIL_WIDTH + 2)
        pygame.draw.circle(temp_surf, p_color, points[i], (TRAIL_WIDTH // 2) + 1)
    pygame.draw.circle(temp_surf, p_color, points[-1], (TRAIL_WIDTH // 2) + 1)
    surf.blit(temp_surf, (0, 0))

    solid_mask = pygame.mask.from_surface(surf)
    empty_mask = solid_mask.copy()
    empty_mask.invert()

    edge_mask = pygame.mask.Mask((MAP_WIDTH, MAP_HEIGHT))
    edge_mask.fill()
    inner_mask = pygame.mask.Mask((MAP_WIDTH - 2, MAP_HEIGHT - 2))
    inner_mask.fill()
    edge_mask.erase(inner_mask, (1, 1))

    for comp in empty_mask.connected_components():
        if not comp.overlap(edge_mask, (0, 0)):
            enclosed_surf = comp.to_surface(setcolor=p_color, unsetcolor=(0, 0, 0, 0))
            surf.blit(enclosed_surf, (0, 0))


map_background = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
map_background.fill(BLACK)
pygame.draw.circle(map_background, WHITE, (MAP_CENTER_X, MAP_CENTER_Y), MAP_RADIUS)

my_id = None
my_color = (0, 0, 255)
game_state = "LOBBY"


def sync_world_data(byte_reply):
    global game_state
    try:
        data_str = byte_reply.decode('utf8')
        sections = data_str.split('~')
        if sections[0] != 'WRLDR': return []

        players_list = []
        capture_section = False

        for section in sections[1:]:
            if section == 'CAPT':
                capture_section = True
                continue

            if not section.strip(): continue

            if not capture_section:
                parts = section.split(',')
                uid = parts[0]
                px, py = int(parts[1]), int(parts[2])
                alive = parts[3] == '1'
                r, g, b = int(parts[4]), int(parts[5]), int(parts[6])

                trail_pts = []
                if len(parts) > 7 and parts[7]:
                    pairs = parts[7].split('|')
                    for pair in pairs:
                        coords = pair.split(':')
                        trail_pts.append((int(coords[0]), int(coords[1])))

                players_list.append(
                    {'id': uid, 'x': px, 'y': py, 'alive': alive, 'color': (r, g, b), 'trail': trail_pts})

                # Check personal vitals -> trigger DEATH state
                if uid == my_id and not alive:
                    game_state = "DEAD"
            else:
                parts = section.split(',')
                cid = parts[0]
                if not parts[1]: continue

                cap_pts = []
                pairs = parts[1].split('|')
                for pair in pairs:
                    coords = pair.split(':')
                    cap_pts.append((int(coords[0]), int(coords[1])))

                if cid in puddle_surfaces:
                    target_color = next((p['color'] for p in players_list if p['id'] == cid), (0, 0, 255))
                    draw_local_capture(puddle_surfaces[cid], cap_pts, target_color)

        return players_list
    except Exception as e:
        print(f"Error parsing sync tracking data: {e}")
        return []


def main(server_ip):
    global game_state, my_id, my_color, puddle_surfaces

    sock = socket.socket()
    try:
        sock.connect((server_ip, 1233))
    except Exception as e:
        print(f"Failed connecting to server {server_ip}: {e}")
        return

    running = True
    active_players = []

    while running:
        # 1. EVENT LAYER
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if my_id: send_with_size(sock, f"EXIT~{my_id}".encode())
                running = False

            if game_state == "LOBBY" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if start_button_rect.collidepoint(event.pos):
                    send_with_size(sock, b"JOIN")
                    reply = recv_by_size(sock).decode('utf8').split('~')
                    if reply[0] == 'JOINR':
                        my_id = reply[1]
                        c_parts = reply[2].split(',')
                        my_color = (int(c_parts[0]), int(c_parts[1]), int(c_parts[2]))
                        puddle_surfaces.clear()
                        game_state = "WAITING"
                    else:
                        print("Could not join:", reply)

        # 2. LOGIC & COMM LAYER
        if game_state == "LOBBY":
            screen.fill(BLACK)
            title_text = font.render("PUDDLE WORLD MP", True, WHITE)
            screen.blit(title_text, (WINDOW_WIDTH // 2 - title_text.get_width() // 2, WINDOW_HEIGHT // 4))

            button_color = TRAIL_ALPHA_COLOR if start_button_rect.collidepoint(
                pygame.mouse.get_pos()) else PUDDLE_BASE_COLOR
            pygame.draw.rect(screen, button_color, start_button_rect, border_radius=12)

            btn_text = button_font.render("START GAME", True, WHITE)
            screen.blit(btn_text, (start_button_rect.centerx - btn_text.get_width() // 2,
                                   start_button_rect.centery - btn_text.get_height() // 2))

        elif game_state == "WAITING":
            send_with_size(sock, f"UPDT~{my_id}~0~0".encode())
            reply_bytes = recv_by_size(sock)
            if not reply_bytes: break

            reply_str = reply_bytes.decode('utf8')

            if reply_str.startswith("WAIT"):
                parts = reply_str.split('~')
                screen.fill(BLACK)
                title_text = font.render(f"WAITING ROOM", True, WHITE)
                count_text = button_font.render(f"{parts[1]} / {parts[2]} PLAYERS CONNECTED", True, TRAIL_ALPHA_COLOR)

                screen.blit(title_text, (WINDOW_WIDTH // 2 - title_text.get_width() // 2, WINDOW_HEIGHT // 3))
                screen.blit(count_text, (WINDOW_WIDTH // 2 - count_text.get_width() // 2, WINDOW_HEIGHT // 2))

            elif reply_str.startswith("WRLDR"):
                game_state = "GAME"
                active_players = sync_world_data(reply_bytes)

                for p in active_players:
                    if p['id'] not in puddle_surfaces:
                        px = p['x'] + PLAYER_WIDTH // 2
                        py = p['y'] + PLAYER_HEIGHT // 2
                        puddle_surfaces[p['id']] = create_local_puddle(p['color'], px, py)

        elif game_state == "GAME":
            my_struct = next((p for p in active_players if p['id'] == my_id), None)
            cam_x, cam_y = 0, 0

            if my_struct:
                cam_x = int(my_struct['x'] + PLAYER_WIDTH / 2 - WINDOW_WIDTH / 2)
                cam_y = int(my_struct['y'] + PLAYER_HEIGHT / 2 - WINDOW_HEIGHT / 2)

                m_screen_x, m_screen_y = pygame.mouse.get_pos()
                m_map_x = cam_x + m_screen_x
                m_map_y = cam_y + m_screen_y

                dx = m_map_x - (my_struct['x'] + PLAYER_WIDTH / 2)
                dy = m_map_y - (my_struct['y'] + PLAYER_HEIGHT / 2)
            else:
                dx, dy = 0, 0

            send_with_size(sock, f"UPDT~{my_id}~{dx}~{dy}".encode())
            reply_bytes = recv_by_size(sock)
            active_players = sync_world_data(reply_bytes)

            # --- EXIT ON DEATH ---
            # If the sync function registered that we died, clear data and leave to lobby
            if game_state == "DEAD":
                send_with_size(sock, f"EXIT~{my_id}".encode())
                my_id = None
                puddle_surfaces.clear()
                active_players = []
                game_state = "LOBBY"
                continue  # Skip drawing this frame and go straight to lobby

            for p in active_players:
                if p['id'] not in puddle_surfaces:
                    px = p['x'] + PLAYER_WIDTH // 2
                    py = p['y'] + PLAYER_HEIGHT // 2
                    puddle_surfaces[p['id']] = create_local_puddle(p['color'], px, py)

            # 3. DRAWING LAYER
            screen.fill(BLACK)
            screen.blit(map_background, (-cam_x, -cam_y))

            for p in active_players:
                if not p['alive'] or len(p['trail']) < 2: continue
                t_color = (p['color'][0], p['color'][1], p['color'][2], 180)
                for i in range(len(p['trail']) - 1):
                    start = (p['trail'][i][0] - cam_x, p['trail'][i][1] - cam_y)
                    end = (p['trail'][i + 1][0] - cam_x, p['trail'][i + 1][1] - cam_y)
                    pygame.draw.line(screen, t_color, start, end, TRAIL_WIDTH)
                    pygame.draw.circle(screen, t_color, start, TRAIL_WIDTH // 2)
                pygame.draw.circle(screen, t_color, (p['trail'][-1][0] - cam_x, p['trail'][-1][1] - cam_y),
                                   TRAIL_WIDTH // 2)

            for p_id, p_surf in puddle_surfaces.items():
                if any(p['id'] == p_id for p in active_players):
                    screen.blit(p_surf, (-cam_x, -cam_y))

            for p in active_players:
                if not p['alive']: continue

                p_surf = pygame.Surface((PLAYER_WIDTH, PLAYER_HEIGHT), pygame.SRCALPHA)
                p_surf.fill(p['color'])
                pygame.draw.rect(p_surf, WHITE, (PLAYER_WIDTH - 10, PLAYER_HEIGHT // 2 - 4, 8, 8))

                angle = 0
                if p['id'] == my_id and (dx != 0 or dy != 0):
                    angle = math.degrees(math.atan2(dy, dx))

                rot_surf = pygame.transform.rotate(p_surf, -angle)

                if p['id'] == my_id:
                    rect = rot_surf.get_rect(
                        center=(PLAYER_SCREEN_X + PLAYER_WIDTH // 2, PLAYER_SCREEN_Y + PLAYER_HEIGHT // 2))
                else:
                    rect = rot_surf.get_rect(
                        center=(p['x'] + PLAYER_WIDTH // 2 - cam_x, p['y'] + PLAYER_HEIGHT // 2 - cam_y))

                screen.blit(rot_surf, rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sock.close()


if __name__ == '__main__':
    target_ip = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    main(target_ip)