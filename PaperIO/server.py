__author__ = 'Tom Wallerstein'

from tcp_by_size import TcpBySize
import socket
import threading
import math
import pygame
import random
import auth
from encryption import (
    generate_rsa_keys, rsa_decrypt,
    dh_generate_private, dh_compute_public, dh_compute_shared,
    dh_derive_aes_key, DH_PRIME, DH_GENERATOR
)

pygame.init()

# ====================== CONSTANTS ======================
MAP_RADIUS = 1000
MAP_CENTER_X = MAP_RADIUS
MAP_CENTER_Y = MAP_RADIUS
MAP_WIDTH = MAP_RADIUS * 2
MAP_HEIGHT = MAP_RADIUS * 2

PLAYER_WIDTH = 35
PLAYER_HEIGHT = 35
PLAYER_SPEED = 4
TRAIL_WIDTH = PLAYER_WIDTH
PUDDLE_RADIUS = 90

REQUIRED_PLAYERS = 2

print("Generating Server RSA Keys...")
RSA_PRIVATE_PEM, RSA_PUBLIC_PEM = generate_rsa_keys()
print("Keys Generated.")


# ====================== PUDDLE SPLIT LOGIC ======================
def enforce_puddle_connectivity(p_surf, px, py, trail_pts, last_pos):
    """
    Checks if a puddle has been split into pieces. Keeps only the piece
    that the player is currently touching or rooted to.
    """
    mask = pygame.mask.from_surface(p_surf)
    safe_pt = None

    # 1. Check direct connection points (Player center, Trail Origin, Last Inside Pos)
    candidates = [(int(px), int(py))]
    if trail_pts and len(trail_pts) > 0:
        candidates.append((int(trail_pts[0][0]), int(trail_pts[0][1])))
    if last_pos:
        candidates.append((int(last_pos[0]), int(last_pos[1])))

    for cx, cy in candidates:
        if 0 <= cx < p_surf.get_width() and 0 <= cy < p_surf.get_height():
            if mask.get_at((cx, cy)):
                safe_pt = (cx, cy)
                break

    # 2. Fallback: If exact edge was clipped, search nearby pixels
    if not safe_pt and last_pos:
        lx, ly = int(last_pos[0]), int(last_pos[1])
        found = False
        for r in range(1, 45):  # Spiral out slightly larger than player width
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if abs(dx) == r or abs(dy) == r:
                        nx, ny = lx + dx, ly + dy
                        if 0 <= nx < p_surf.get_width() and 0 <= ny < p_surf.get_height():
                            if mask.get_at((nx, ny)):
                                safe_pt = (nx, ny)
                                found = True
                                break
                if found: break
            if found: break

    # 3. Rebuild the surface keeping ONLY the connected component
    if safe_pt:
        keep_mask = mask.connected_component(safe_pt)
        if keep_mask.count() == mask.count(): return  # Optimization: not split
        color = p_surf.get_at(safe_pt)
        p_surf.fill((0, 0, 0, 0))
        kept_surf = keep_mask.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))
        p_surf.blit(kept_surf, (0, 0))
    else:
        p_surf.fill((0, 0, 0, 0))  # Completely wiped out


# ====================== GAME STATE MANAGER ======================
class PlayerSession:
    def __init__(self, player_id):
        self.id = player_id
        self.x = 0
        self.y = 0
        self.alive = True
        self.was_inside_puddle = True
        self.trail_points = []
        self.color = (random.randint(20, 230), random.randint(20, 230), random.randint(20, 230))
        self.last_inside_pos = (0, 0)
        self.puddle_surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
        self.unread_captures = []

    def set_spawn(self, cx, cy):
        self.x = cx - PLAYER_WIDTH / 2.0
        self.y = cy - PLAYER_HEIGHT / 2.0
        self.last_inside_pos = (cx, cy)
        self.puddle_surface.fill((0, 0, 0, 0))
        pygame.draw.circle(self.puddle_surface, (255, 255, 255, 255), (cx, cy), PUDDLE_RADIUS)


class GameState:
    def __init__(self):
        self.players = {}
        self.lock = threading.Lock()
        self.phase = "WAITING"
        self.required_players = REQUIRED_PLAYERS

    def add_player(self, requested_id):
        with self.lock:
            if self.phase == "PLAYING": return None
            if self.phase == "GAMEOVER":
                self.players.clear()
                self.phase = "WAITING"
            if requested_id in self.players: return None
            p_id = requested_id
            self.players[p_id] = PlayerSession(p_id)
            if len(self.players) >= self.required_players: self._start_game()
            return p_id

    def remove_player(self, p_id):
        with self.lock:
            if p_id in self.players: del self.players[p_id]
            if len(self.players) == 0: self.phase = "WAITING"

    def _start_game(self):
        self.phase = "PLAYING"
        spawn_radius = MAP_RADIUS * 0.6
        angle_step = (2 * math.pi) / len(self.players)
        for i, p_id in enumerate(self.players.keys()):
            angle = i * angle_step
            cx = MAP_CENTER_X + spawn_radius * math.cos(angle)
            cy = MAP_CENTER_Y + spawn_radius * math.sin(angle)
            self.players[p_id].set_spawn(cx, cy)

    def process_movement(self, p_id, dx, dy):
        with self.lock:
            if self.phase != "PLAYING": return
            if p_id not in self.players or not self.players[p_id].alive: return

            p = self.players[p_id]
            distance = math.hypot(dx, dy)
            if distance > 0:
                p.x += (dx / distance) * PLAYER_SPEED
                p.y += (dy / distance) * PLAYER_SPEED
                cx = p.x + PLAYER_WIDTH / 2
                cy = p.y + PLAYER_HEIGHT / 2
                dist_from_center = math.hypot(cx - MAP_CENTER_X, cy - MAP_CENTER_Y)
                if dist_from_center > MAP_RADIUS - PLAYER_WIDTH / 2:
                    angle = math.atan2(cy - MAP_CENTER_Y, cx - MAP_CENTER_X)
                    p.x = MAP_CENTER_X - PLAYER_WIDTH / 2 + math.cos(angle) * (MAP_RADIUS - PLAYER_WIDTH / 2)
                    p.y = MAP_CENTER_Y - PLAYER_HEIGHT / 2 + math.sin(angle) * (MAP_RADIUS - PLAYER_HEIGHT / 2)

            p_center = (p.x + PLAYER_WIDTH / 2, p.y + PLAYER_HEIGHT / 2)
            px, py = int(p_center[0]), int(p_center[1])

            is_inside = (0 <= px < MAP_WIDTH and 0 <= py < MAP_HEIGHT and p.puddle_surface.get_at((px, py))[3] > 0)

            if is_inside:
                p.last_inside_pos = p_center
            else:
                if p.was_inside_puddle: p.trail_points.append(p.last_inside_pos)
                if not p.trail_points or math.hypot(p.trail_points[-1][0] - p_center[0],
                                                    p.trail_points[-1][1] - p_center[1]) > 3:
                    p.trail_points.append(p_center)

            if is_inside and not p.was_inside_puddle:
                p.trail_points.append(p_center)
                if len(p.trail_points) >= 2:
                    xs = [pt[0] for pt in p.trail_points]
                    ys = [pt[1] for pt in p.trail_points]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)

                    margin = int(TRAIL_WIDTH + 15)
                    bx1 = max(0, int(min_x - margin))
                    by1 = max(0, int(min_y - margin))
                    bx2 = min(MAP_WIDTH, int(max_x + margin))
                    by2 = min(MAP_HEIGHT, int(max_y + margin))
                    bw = bx2 - bx1
                    bh = by2 - by1

                    if bw > 0 and bh > 0:
                        sub_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
                        sub_surf.blit(p.puddle_surface, (0, 0), pygame.Rect(bx1, by1, bw, bh))

                        for i in range(len(p.trail_points) - 1):
                            p1 = (p.trail_points[i][0] - bx1, p.trail_points[i][1] - by1)
                            p2 = (p.trail_points[i + 1][0] - bx1, p.trail_points[i + 1][1] - by1)
                            pygame.draw.line(sub_surf, (255, 255, 255, 255), p1, p2, TRAIL_WIDTH + 2)
                            pygame.draw.circle(sub_surf, (255, 255, 255, 255), p1, (TRAIL_WIDTH // 2) + 1)
                        p_last = (p.trail_points[-1][0] - bx1, p.trail_points[-1][1] - by1)
                        pygame.draw.circle(sub_surf, (255, 255, 255, 255), p_last, (TRAIL_WIDTH // 2) + 1)

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

                        holes_surf = holes_mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
                        p.puddle_surface.blit(holes_surf, (bx1, by1))

                        for i in range(len(p.trail_points) - 1):
                            pygame.draw.line(p.puddle_surface, (255, 255, 255, 255), p.trail_points[i],
                                             p.trail_points[i + 1], TRAIL_WIDTH + 2)
                            pygame.draw.circle(p.puddle_surface, (255, 255, 255, 255), p.trail_points[i],
                                               (TRAIL_WIDTH // 2) + 1)
                        pygame.draw.circle(p.puddle_surface, (255, 255, 255, 255), p.trail_points[-1],
                                           (TRAIL_WIDTH // 2) + 1)

                        trail_only_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
                        for i in range(len(p.trail_points) - 1):
                            p1 = (p.trail_points[i][0] - bx1, p.trail_points[i][1] - by1)
                            p2 = (p.trail_points[i + 1][0] - bx1, p.trail_points[i + 1][1] - by1)
                            pygame.draw.line(trail_only_surf, (255, 255, 255, 255), p1, p2, TRAIL_WIDTH + 2)
                            pygame.draw.circle(trail_only_surf, (255, 255, 255, 255), p1, (TRAIL_WIDTH // 2) + 1)
                        pygame.draw.circle(trail_only_surf, (255, 255, 255, 255), p_last, (TRAIL_WIDTH // 2) + 1)

                        trail_only_mask = pygame.mask.from_surface(trail_only_surf)
                        stolen_sub_mask = holes_mask.copy()
                        stolen_sub_mask.draw(trail_only_mask, (0, 0))

                        erase_surf = stolen_sub_mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))

                        for enemy_id, enemy in self.players.items():
                            if enemy_id != p_id:
                                # 1. Erase the stolen chunk
                                enemy.puddle_surface.blit(erase_surf, (bx1, by1), special_flags=pygame.BLEND_RGBA_SUB)
                                # 2. Enforce Puddle Split Mechanics
                                ex = enemy.x + PLAYER_WIDTH / 2
                                ey = enemy.y + PLAYER_HEIGHT / 2
                                enforce_puddle_connectivity(enemy.puddle_surface, ex, ey, enemy.trail_points,
                                                            enemy.last_inside_pos)

                        for target_player in self.players.values():
                            target_player.unread_captures.append((p_id, list(p.trail_points)))

                p.trail_points = []

            p.was_inside_puddle = is_inside
            self._check_collisions(p_id, p_center)

    def _check_collisions(self, current_id, p_center):
        def point_to_segment_dist(p, a, b):
            px, py = p
            ax, ay = a
            bx, by = b
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0: return math.hypot(px - ax, py - ay)
            t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

        hitbox_radius = PLAYER_WIDTH / 2 - 2
        for enemy_id, enemy in self.players.items():
            if not enemy.alive or len(enemy.trail_points) < 2: continue
            safe_index = len(enemy.trail_points) - 1
            if enemy_id == current_id:
                path_dist = 0
                while safe_index > 0:
                    path_dist += math.hypot(enemy.trail_points[safe_index][0] - enemy.trail_points[safe_index - 1][0],
                                            enemy.trail_points[safe_index][1] - enemy.trail_points[safe_index - 1][1])
                    safe_index -= 1
                    if path_dist > PLAYER_WIDTH * 2: break

            for i in range(safe_index):
                dist = point_to_segment_dist(p_center, enemy.trail_points[i], enemy.trail_points[i + 1])
                if dist < hitbox_radius + (TRAIL_WIDTH / 2):
                    self.players[enemy_id].alive = False
                    self.players[enemy_id].trail_points = []
                    self.players[enemy_id].puddle_surface.fill((0, 0, 0, 0))
                    return


shared_game = GameState()


# ====================== PROTOCOL ROUTER ======================
def protocol_build_reply(req_str):
    try:
        fields = req_str.split('~')
        code = fields[0]

        if code == 'SIGN':
            if len(fields) < 3: return "SIGNR~ERR~Missing fields"
            success, msg = auth.signup_user(fields[1], fields[2])
            if success: return "SIGNR~OK"
            return f"SIGNR~ERR~{msg}"

        elif code == 'LOGN':
            if len(fields) < 3: return "LOGNR~ERR~Missing fields"
            success, msg = auth.login_user(fields[1], fields[2])
            if success: return f"LOGNR~OK~{fields[1]}"
            return f"LOGNR~ERR~{msg}"

        elif code == 'JOIN':
            p_id = shared_game.add_player(fields[1])
            if not p_id: return "ERRR~Match already in progress!"
            p = shared_game.players[p_id]
            return f"JOINR~{p_id}~{p.color[0]},{p.color[1]},{p.color[2]}"

        elif code == 'UPDT':
            if shared_game.phase == "WAITING":
                curr = len(shared_game.players)
                req = shared_game.required_players
                return f"WAIT~{curr}~{req}"

            p_id = fields[1]
            dx, dy = float(fields[2]), float(fields[3])

            shared_game.process_movement(p_id, dx, dy)

            player_strings = []
            with shared_game.lock:
                for uid, p in shared_game.players.items():
                    trail_str = "|".join([f"{int(pt[0])}:{int(pt[1])}" for pt in p.trail_points])
                    p_str = f"{uid},{int(p.x)},{int(p.y)},{1 if p.alive else 0},{p.color[0]},{p.color[1]},{p.color[2]},{trail_str}"
                    player_strings.append(p_str)

            cap_strings = []
            with shared_game.lock:
                if p_id in shared_game.players:
                    for cid, pts in shared_game.players[p_id].unread_captures:
                        pts_str = "|".join([f"{int(pt[0])}:{int(pt[1])}" for pt in pts])
                        cap_strings.append(f"{cid},{pts_str}")
                    shared_game.players[p_id].unread_captures.clear()

            reply_str = "WRLDR~" + "~".join(player_strings)
            if cap_strings:
                reply_str += "~CAPT~" + "~".join(cap_strings)
            return reply_str

        elif code == 'EXIT':
            shared_game.remove_player(fields[1])
            return 'EXTR'

    except Exception as e:
        print(f"Protocol packing error: {e}")

    return 'ERRR~001~Internal Error'


# ====================== ENCRYPTION HANDSHAKE ======================
def do_key_exchange(conn):
    method_msg = conn.recv()
    if not method_msg.startswith("METHOD|"): return False
    method = method_msg.split("|", 1)[1].upper()
    if method not in ("RSA", "DH"):
        conn.send("METHOD_FAIL|Unsupported method")
        return False
    conn.send("METHOD_OK")
    if method == "RSA":
        req = conn.recv()
        if req != "PUBKEY_REQ": return False
        conn.send("PUBKEY|" + RSA_PUBLIC_PEM.hex())
        key_msg = conn.recv()
        if not key_msg.startswith("KEY|"): return False
        encrypted_aes = bytes.fromhex(key_msg.split("|", 1)[1])
        aes_key = rsa_decrypt(encrypted_aes, RSA_PRIVATE_PEM)
        conn.send("KEY_OK")
        conn.key = aes_key
        return True
    else:
        server_private = dh_generate_private()
        server_public = dh_compute_public(server_private)
        conn.send(f"DH_PARAMS|{DH_PRIME:x}|{DH_GENERATOR}|{server_public:x}")
        resp = conn.recv()
        if not resp.startswith("DH_KEY|"): return False
        client_public = int(resp.split("|", 1)[1], 16)
        shared = dh_compute_shared(client_public, server_private)
        aes_key = dh_derive_aes_key(shared)
        conn.send("KEY_OK")
        conn.key = aes_key
        return True


def handle_client(sock, tid, addr):
    p_id = None
    try:
        conn = TcpBySize(sock)
        if not do_key_exchange(conn):
            print(f"Key exchange failed for {addr}")
            sock.close()
            return
        print(f"Secure connection established with {addr}")
        while True:
            str_data = conn.recv()
            if not str_data: break
            if str_data.startswith('UPDT') or str_data.startswith('EXIT'):
                parts = str_data.split('~')
                if len(parts) > 1: p_id = parts[1]
            to_send = protocol_build_reply(str_data)
            conn.send(to_send)
    except Exception as e:
        pass
    finally:
        if p_id: shared_game.remove_player(p_id)
        sock.close()


def main():
    srv_sock = socket.socket()
    srv_sock.bind(('0.0.0.0', 1233))
    srv_sock.listen(20)
    srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    i = 1
    print(f"Multiplayer Secure Server running. Waiting for {REQUIRED_PLAYERS} players...")
    while True:
        cli_sock, addr = srv_sock.accept()
        t = threading.Thread(target=handle_client, args=(cli_sock, str(i), addr))
        t.daemon = True
        t.start()
        i += 1


if __name__ == '__main__':
    main()