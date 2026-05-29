from tcp_by_size import TcpBySize
import socket
import sys
import math
import pygame
from encryption import (
    generate_aes_key, rsa_encrypt,
    dh_generate_private, dh_compute_public, dh_compute_shared, dh_derive_aes_key
)

# ====================== CONSTANTS ======================
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

MAP_RADIUS = 1000
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
pygame.display.set_caption("Secure Paper.io Multiplayer")
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


def apply_local_capture(p_id, points, color, surfaces_dict):
    if len(points) < 2: return

    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    margin = int(TRAIL_WIDTH + 15)
    bx1 = max(0, int(min_x - margin))
    by1 = max(0, int(min_y - margin))
    bx2 = min(MAP_WIDTH, int(max_x + margin))
    by2 = min(MAP_HEIGHT, int(max_y + margin))
    bw = bx2 - bx1
    bh = by2 - by1

    if bw <= 0 or bh <= 0: return

    surf = surfaces_dict[p_id]
    p_color = (max(0, color[0] - 40), max(0, color[1] - 40), max(0, color[2] - 40), 255)

    sub_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
    sub_surf.blit(surf, (0, 0), pygame.Rect(bx1, by1, bw, bh))

    for i in range(len(points) - 1):
        p1 = (points[i][0] - bx1, points[i][1] - by1)
        p2 = (points[i + 1][0] - bx1, points[i + 1][1] - by1)
        pygame.draw.line(sub_surf, p_color, p1, p2, TRAIL_WIDTH + 2)
        pygame.draw.circle(sub_surf, p_color, p1, (TRAIL_WIDTH // 2) + 1)
    p_last = (points[-1][0] - bx1, points[-1][1] - by1)
    pygame.draw.circle(sub_surf, p_color, p_last, (TRAIL_WIDTH // 2) + 1)

    sub_mask = pygame.mask.from_surface(sub_surf)
    sub_empty_mask = pygame.mask.Mask((bw, bh), fill=True)
    sub_empty_mask.erase(sub_mask, (0, 0))

    reached_outside = pygame.mask.Mask((bw, bh), fill=False)
    border_pts = []
    for x in range(bw):
        border_pts.append((x, 0))
        border_pts.append((x, bh - 1))
    for y in range(1, bh - 1):
        border_pts.append((0, y))
        border_pts.append((bw - 1, y))

    for pt in border_pts:
        if sub_empty_mask.get_at(pt) and not reached_outside.get_at(pt):
            comp = sub_empty_mask.connected_component(pt)
            reached_outside.draw(comp, (0, 0))

    holes_mask = sub_empty_mask.copy()
    holes_mask.erase(reached_outside, (0, 0))

    holes_surf = holes_mask.to_surface(setcolor=p_color, unsetcolor=(0, 0, 0, 0))
    surf.blit(holes_surf, (bx1, by1))

    for i in range(len(points) - 1):
        pygame.draw.line(surf, p_color, points[i], points[i + 1], TRAIL_WIDTH + 2)
        pygame.draw.circle(surf, p_color, points[i], (TRAIL_WIDTH // 2) + 1)
    pygame.draw.circle(surf, p_color, points[-1], (TRAIL_WIDTH // 2) + 1)

    trail_only_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
    for i in range(len(points) - 1):
        p1 = (points[i][0] - bx1, points[i][1] - by1)
        p2 = (points[i + 1][0] - bx1, points[i + 1][1] - by1)
        pygame.draw.line(trail_only_surf, (255, 255, 255, 255), p1, p2, TRAIL_WIDTH + 2)
        pygame.draw.circle(trail_only_surf, (255, 255, 255, 255), p1, (TRAIL_WIDTH // 2) + 1)
    pygame.draw.circle(trail_only_surf, (255, 255, 255, 255), p_last, (TRAIL_WIDTH // 2) + 1)

    trail_only_mask = pygame.mask.from_surface(trail_only_surf)
    stolen_sub_mask = holes_mask.copy()
    stolen_sub_mask.draw(trail_only_mask, (0, 0))

    erase_surf = stolen_sub_mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))

    for other_id, other_surf in surfaces_dict.items():
        if other_id != p_id:
            other_surf.blit(erase_surf, (bx1, by1), special_flags=pygame.BLEND_RGBA_SUB)


map_background = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
map_background.fill(BLACK)
pygame.draw.circle(map_background, WHITE, (MAP_CENTER_X, MAP_CENTER_Y), MAP_RADIUS)

my_id = None
my_color = (0, 0, 255)
game_state = "LOBBY"


def sync_world_data(str_reply):
    global game_state
    try:
        sections = str_reply.split('~')
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
                    apply_local_capture(cid, cap_pts, target_color, puddle_surfaces)

        return players_list
    except Exception as e:
        print(f"Error parsing sync tracking data: {e}")
        return []


# ====================== ENCRYPTION HANDSHAKE ======================
def connect_securely(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((ip, port))
        conn = TcpBySize(sock)

        # We will hardcode to DH for the game, just to ensure high security
        method = "DH"

        conn.send(f"METHOD|{method}")
        resp = conn.recv()

        if resp.startswith("METHOD_FAIL"):
            print("Server rejected method.")
            return None

        if method == "RSA":
            conn.send("PUBKEY_REQ")
            resp = conn.recv()
            if not resp.startswith("PUBKEY|"): return None
            pub_pem = bytes.fromhex(resp.split("|", 1)[1])

            aes_key = generate_aes_key()
            encrypted = rsa_encrypt(aes_key, pub_pem)
            conn.send("KEY|" + encrypted.hex())

            ack = conn.recv()
            if ack != "KEY_OK": return None
            conn.key = aes_key

        elif method == "DH":
            resp = conn.recv()
            if not resp.startswith("DH_PARAMS|"): return None
            parts = resp.split("|")
            p = int(parts[1], 16)
            g = int(parts[2])
            server_public = int(parts[3], 16)

            my_private = dh_generate_private()
            my_public = dh_compute_public(my_private)
            conn.send(f"DH_KEY|{my_public:x}")

            shared = dh_compute_shared(server_public, my_private)
            aes_key = dh_derive_aes_key(shared)

            ack = conn.recv()
            if ack != "KEY_OK": return None
            conn.key = aes_key

        return sock, conn
    except Exception as e:
        print(f"Connection failed: {e}")
        return None


def main(server_ip):
    global game_state, my_id, my_color, puddle_surfaces

    print("Establishing secure connection to server...")
    connection_data = connect_securely(server_ip, 1233)

    if not connection_data:
        print("Failed to establish secure connection. Exiting.")
        return

    sock, conn = connection_data
    print("Connection encrypted successfully.")

    running = True
    active_players = []

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if my_id: conn.send(f"EXIT~{my_id}")
                running = False

            if game_state == "LOBBY" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if start_button_rect.collidepoint(event.pos):
                    conn.send("JOIN")
                    reply = conn.recv().split('~')
                    if reply[0] == 'JOINR':
                        my_id = reply[1]
                        c_parts = reply[2].split(',')
                        my_color = (int(c_parts[0]), int(c_parts[1]), int(c_parts[2]))
                        puddle_surfaces.clear()
                        game_state = "WAITING"
                    else:
                        print("Could not join:", reply)

        if game_state == "LOBBY":
            screen.fill(BLACK)
            title_text = font.render("Paper.Tom", True, WHITE)
            screen.blit(title_text, (WINDOW_WIDTH // 2 - title_text.get_width() // 2, WINDOW_HEIGHT // 4))

            button_color = TRAIL_ALPHA_COLOR if start_button_rect.collidepoint(
                pygame.mouse.get_pos()) else PUDDLE_BASE_COLOR
            pygame.draw.rect(screen, button_color, start_button_rect, border_radius=12)

            btn_text = button_font.render("START GAME", True, WHITE)
            screen.blit(btn_text, (start_button_rect.centerx - btn_text.get_width() // 2,
                                   start_button_rect.centery - btn_text.get_height() // 2))

        elif game_state == "WAITING":
            conn.send(f"UPDT~{my_id}~0~0")
            reply_str = conn.recv()
            if not reply_str: break

            if reply_str.startswith("WAIT"):
                parts = reply_str.split('~')
                screen.fill(BLACK)
                title_text = font.render(f"WAITING ROOM", True, WHITE)
                count_text = button_font.render(f"{parts[1]} / {parts[2]} PLAYERS CONNECTED", True, TRAIL_ALPHA_COLOR)

                screen.blit(title_text, (WINDOW_WIDTH // 2 - title_text.get_width() // 2, WINDOW_HEIGHT // 3))
                screen.blit(count_text, (WINDOW_WIDTH // 2 - count_text.get_width() // 2, WINDOW_HEIGHT // 2))

            elif reply_str.startswith("WRLDR"):
                game_state = "GAME"
                active_players = sync_world_data(reply_str)

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

            conn.send(f"UPDT~{my_id}~{dx}~{dy}")
            reply_str = conn.recv()
            active_players = sync_world_data(reply_str)

            active_ids = {p['id'] for p in active_players if p['alive']}
            keys_to_remove = [pid for pid in puddle_surfaces if pid not in active_ids]
            for k in keys_to_remove:
                del puddle_surfaces[k]

            if game_state == "DEAD":
                conn.send(f"EXIT~{my_id}")
                conn.recv()
                my_id = None
                puddle_surfaces.clear()
                active_players = []
                game_state = "LOBBY"
                continue

            for p in active_players:
                if p['id'] not in puddle_surfaces and p['alive']:
                    px = p['x'] + PLAYER_WIDTH // 2
                    py = p['y'] + PLAYER_HEIGHT // 2
                    puddle_surfaces[p['id']] = create_local_puddle(p['color'], px, py)

            screen.fill(BLACK)
            screen.blit(map_background, (-cam_x, -cam_y))

            for p_id, p_surf in puddle_surfaces.items():
                if any(p['id'] == p_id for p in active_players):
                    screen.blit(p_surf, (-cam_x, -cam_y))

            for p in active_players:
                if not p['alive'] or len(p['trail']) < 2: continue
                t_color = (p['color'][0], p['color'][1], p['color'][2], 180)

                trail_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)

                for i in range(len(p['trail']) - 1):
                    start = (p['trail'][i][0] - cam_x, p['trail'][i][1] - cam_y)
                    end = (p['trail'][i + 1][0] - cam_x, p['trail'][i + 1][1] - cam_y)
                    pygame.draw.line(trail_surf, t_color, start, end, TRAIL_WIDTH)
                    pygame.draw.circle(trail_surf, t_color, start, TRAIL_WIDTH // 2)
                pygame.draw.circle(trail_surf, t_color, (p['trail'][-1][0] - cam_x, p['trail'][-1][1] - cam_y),
                                   TRAIL_WIDTH // 2)

                if p['id'] in puddle_surfaces:
                    erase_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
                    erase_surf.blit(puddle_surfaces[p['id']], (-cam_x, -cam_y))
                    trail_surf.blit(erase_surf, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

                screen.blit(trail_surf, (0, 0))

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