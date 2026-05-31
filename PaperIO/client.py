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
GOLD = (255, 215, 0)  # Used for the percentage text

TRAIL_WIDTH = PLAYER_WIDTH
PUDDLE_RADIUS = 90

pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Secure Paper.io Multiplayer")
clock = pygame.time.Clock()

font = pygame.font.Font(None, 74)
button_font = pygame.font.Font(None, 40)
start_button_rect = pygame.Rect(WINDOW_WIDTH // 2 - 125, WINDOW_HEIGHT // 2 - 35, 250, 70)


class TextInputBox:
    def __init__(self, x, y, w, h, placeholder="", is_password=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = (100, 100, 100)
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.is_password = is_password

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = True
                self.color = (200, 200, 200)
            else:
                self.active = False
                self.color = (100, 100, 100)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                pass
            else:
                if len(self.text) < 15 and event.unicode.isprintable() and event.unicode not in ['~', ',', '|', ':']:
                    self.text += event.unicode

    def draw(self, screen, font):
        pygame.draw.rect(screen, self.color, self.rect, 2)
        if self.text:
            display_text = "*" * len(self.text) if self.is_password else self.text
            txt_surf = font.render(display_text, True, WHITE)
        else:
            txt_surf = font.render(self.placeholder, True, (150, 150, 150))
        screen.blit(txt_surf, (self.rect.x + 10, self.rect.y + self.rect.height // 2 - txt_surf.get_height() // 2))


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

    surf = surfaces_dict[p_id]
    trail_rect = pygame.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    base_rect = surf.get_bounding_rect()
    capture_rect = base_rect.union(trail_rect)

    margin = int(TRAIL_WIDTH + 15)
    capture_rect.inflate_ip(margin * 2, margin * 2)
    capture_rect = capture_rect.clip(pygame.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

    bx1, by1 = capture_rect.x, capture_rect.y
    bw, bh = capture_rect.width, capture_rect.height

    if bw <= 0 or bh <= 0: return

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
game_state = "AUTH_CHOOSE"


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

                if uid == my_id and not alive and game_state == "GAME":
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

    # --- MATCH TRACKING VARIABLES ---
    end_screen_start_time = 0
    current_percentage = 0.0
    frame_counter = 0
    max_players_seen = 0
    total_map_area = math.pi * MAP_RADIUS * MAP_RADIUS

    # --- AUTH GUI VARIABLES ---
    username_box = TextInputBox(WINDOW_WIDTH // 2 - 125, WINDOW_HEIGHT // 2 - 50, 250, 40, "Username")
    password_box = TextInputBox(WINDOW_WIDTH // 2 - 125, WINDOW_HEIGHT // 2 + 10, 250, 40, "Password", is_password=True)
    submit_btn_rect = pygame.Rect(WINDOW_WIDTH // 2 - 75, WINDOW_HEIGHT // 2 + 80, 150, 40)
    back_btn_rect = pygame.Rect(20, 20, 100, 40)

    login_btn_rect = pygame.Rect(WINDOW_WIDTH // 2 - 160, WINDOW_HEIGHT // 2, 140, 50)
    signup_btn_rect = pygame.Rect(WINDOW_WIDTH // 2 + 20, WINDOW_HEIGHT // 2, 140, 50)

    auth_mode = ""
    auth_msg = ""
    logged_in_username = ""

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if my_id: conn.send(f"EXIT~{my_id}")
                running = False

            # --- AUTHENTICATION EVENTS ---
            if game_state == "AUTH_CHOOSE":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if login_btn_rect.collidepoint(event.pos):
                        auth_mode = "LOGN"
                        auth_msg = ""
                        username_box.text = ""
                        password_box.text = ""
                        game_state = "AUTH_INPUT"
                    elif signup_btn_rect.collidepoint(event.pos):
                        auth_mode = "SIGN"
                        auth_msg = ""
                        username_box.text = ""
                        password_box.text = ""
                        game_state = "AUTH_INPUT"

            elif game_state == "AUTH_INPUT":
                username_box.handle_event(event)
                password_box.handle_event(event)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if back_btn_rect.collidepoint(event.pos):
                        game_state = "AUTH_CHOOSE"
                    elif submit_btn_rect.collidepoint(event.pos):
                        if username_box.text and password_box.text:
                            conn.send(f"{auth_mode}~{username_box.text}~{password_box.text}")
                            reply_str = conn.recv()
                            reply = reply_str.split('~')

                            if reply[0] == f"{auth_mode}R":
                                if reply[1] == "OK":
                                    if auth_mode == "LOGN":
                                        logged_in_username = username_box.text
                                        game_state = "LOBBY"
                                    else:
                                        auth_msg = "Signup OK! You can now Login."
                                        game_state = "AUTH_CHOOSE"
                                else:
                                    auth_msg = reply[2]

            # --- LOBBY EVENTS ---
            elif game_state == "LOBBY" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if start_button_rect.collidepoint(event.pos):
                    conn.send(f"JOIN~{logged_in_username}")
                    reply = conn.recv().split('~')
                    if reply[0] == 'JOINR':
                        my_id = reply[1]
                        c_parts = reply[2].split(',')
                        my_color = (int(c_parts[0]), int(c_parts[1]), int(c_parts[2]))
                        puddle_surfaces.clear()
                        game_state = "WAITING"
                    else:
                        print("Could not join:", reply)

        # --- DRAW AUTHENTICATION CHOOSE STATE ---
        if game_state == "AUTH_CHOOSE":
            screen.fill(BLACK)
            title_text = font.render("Secure Paper.io", True, WHITE)
            screen.blit(title_text, (WINDOW_WIDTH // 2 - title_text.get_width() // 2, WINDOW_HEIGHT // 4))

            pygame.draw.rect(screen, PUDDLE_BASE_COLOR, login_btn_rect, border_radius=8)
            pygame.draw.rect(screen, PUDDLE_BASE_COLOR, signup_btn_rect, border_radius=8)

            l_txt = button_font.render("LOGIN", True, WHITE)
            s_txt = button_font.render("SIGNUP", True, WHITE)
            screen.blit(l_txt, (login_btn_rect.centerx - l_txt.get_width() // 2,
                                login_btn_rect.centery - l_txt.get_height() // 2))
            screen.blit(s_txt, (signup_btn_rect.centerx - s_txt.get_width() // 2,
                                signup_btn_rect.centery - s_txt.get_height() // 2))

            if auth_msg:
                msg_color = GOLD if "OK" in auth_msg else (255, 50, 50)
                msg_surf = button_font.render(auth_msg, True, msg_color)
                screen.blit(msg_surf, (WINDOW_WIDTH // 2 - msg_surf.get_width() // 2, WINDOW_HEIGHT - 100))

        # --- DRAW AUTHENTICATION INPUT STATE ---
        elif game_state == "AUTH_INPUT":
            screen.fill(BLACK)
            title = "LOGIN" if auth_mode == "LOGN" else "SIGNUP"
            title_text = font.render(title, True, WHITE)
            screen.blit(title_text, (WINDOW_WIDTH // 2 - title_text.get_width() // 2, WINDOW_HEIGHT // 4 - 30))

            username_box.draw(screen, button_font)
            password_box.draw(screen, button_font)

            pygame.draw.rect(screen, PUDDLE_BASE_COLOR, submit_btn_rect, border_radius=8)
            sub_txt = button_font.render("SUBMIT", True, WHITE)
            screen.blit(sub_txt, (submit_btn_rect.centerx - sub_txt.get_width() // 2,
                                  submit_btn_rect.centery - sub_txt.get_height() // 2))

            pygame.draw.rect(screen, (100, 100, 100), back_btn_rect, border_radius=8)
            back_txt = button_font.render("BACK", True, WHITE)
            screen.blit(back_txt, (back_btn_rect.centerx - back_txt.get_width() // 2,
                                   back_btn_rect.centery - back_txt.get_height() // 2))

            if auth_msg:
                msg_surf = button_font.render(auth_msg, True, (255, 50, 50))
                screen.blit(msg_surf, (WINDOW_WIDTH // 2 - msg_surf.get_width() // 2, WINDOW_HEIGHT - 100))

        # --- DRAW LOBBY STATE ---
        elif game_state == "LOBBY":
            screen.fill(BLACK)

            welcome_txt = button_font.render(f"Welcome, {logged_in_username}!", True, GOLD)
            screen.blit(welcome_txt, (WINDOW_WIDTH // 2 - welcome_txt.get_width() // 2, 50))

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

                # Reset match variables when transitioning into the game
                current_percentage = 0.0
                frame_counter = 0
                max_players_seen = len(active_players)

                for p in active_players:
                    if p['id'] not in puddle_surfaces:
                        px = p['x'] + PLAYER_WIDTH // 2
                        py = p['y'] + PLAYER_HEIGHT // 2
                        puddle_surfaces[p['id']] = create_local_puddle(p['color'], px, py)

        elif game_state in ("GAME", "DEAD"):
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

            if game_state == "GAME":
                conn.send(f"UPDT~{my_id}~{dx}~{dy}")
                reply_str = conn.recv()
                active_players = sync_world_data(reply_str)

            active_ids = {p['id'] for p in active_players if p['alive']}
            keys_to_remove = [pid for pid in puddle_surfaces if pid not in active_ids]
            for k in keys_to_remove:
                del puddle_surfaces[k]

            frame_counter += 1
            max_players_seen = max(max_players_seen, len(active_players))

            # Calculate captured area efficiently (every 15 frames to prevent lag)
            if my_id in puddle_surfaces and frame_counter % 15 == 0:
                my_mask = pygame.mask.from_surface(puddle_surfaces[my_id])
                current_percentage = (my_mask.count() / total_map_area) * 100

            alive_others = [p for p in active_players if p['alive'] and p['id'] != my_id]

            if game_state == "DEAD":
                conn.send(f"EXIT~{my_id}")
                try:
                    conn.recv()
                except:
                    pass  # Ignore if server already closed the socket
                game_state = "LOST"
                end_screen_start_time = pygame.time.get_ticks()
                continue
            elif max_players_seen > 1 and len(alive_others) == 0:
                conn.send(f"EXIT~{my_id}")
                try:
                    conn.recv()
                except:
                    pass
                game_state = "WON"
                end_screen_start_time = pygame.time.get_ticks()
                continue
            elif current_percentage >= 99.0:
                conn.send(f"EXIT~{my_id}")
                try:
                    conn.recv()
                except:
                    pass
                game_state = "WON"
                end_screen_start_time = pygame.time.get_ticks()
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

            # --- DRAW PERCENTAGE ---
            perc_text = button_font.render(f"Captured: {current_percentage:.1f}%", True, GOLD)
            screen.blit(perc_text, (WINDOW_WIDTH - perc_text.get_width() - 20, 20))

        elif game_state in ("LOST", "WON"):
            screen.fill(BLACK)
            msg = "YOU WIN!" if game_state == "WON" else "YOU LOSE!"
            color = GOLD if game_state == "WON" else (255, 50, 50)

            text_surf = font.render(msg, True, color)
            screen.blit(text_surf, (WINDOW_WIDTH // 2 - text_surf.get_width() // 2,
                                    WINDOW_HEIGHT // 2 - text_surf.get_height() // 2))

            # Wait exactly 2 seconds (2000 milliseconds) before returning to the lobby
            if pygame.time.get_ticks() - end_screen_start_time > 2000:
                my_id = None
                puddle_surfaces.clear()
                active_players = []
                game_state = "LOBBY"

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sock.close()


if __name__ == '__main__':
    target_ip = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    main(target_ip)