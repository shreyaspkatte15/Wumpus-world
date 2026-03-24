#wumpus_min.py
import streamlit as st
import random
import time
import io
import csv
import os
import base64
from collections import deque

# --------- Configurable parameters ---------
MIN_GRID = 3
MAX_GRID = 10
DEFAULT_GRID = 4
RETURN_POS = (0, 0)
MOVE_DELAY = 1.0  # fixed animation speed: 1 second
ASSETS_DIR = "assets"  # folder with your PNGs

# ---------- Helper to embed images ----------
def get_img_data_uri(filename, size_px=None):
    """Return an inline data URI for a PNG in assets/ or None if missing."""
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    size_attr = ""
    if size_px:
        size_attr = f" width='{size_px}' height='{size_px}' "
    return f"<img src='data:image/png;base64,{data}' {size_attr} style='vertical-align:middle;'/>"

# Preload images (use None fallback if file not found)
IMG_AGENT = get_img_data_uri("agent.png", 44)
IMG_WUMPUS = get_img_data_uri("wumpus.png", 44)
IMG_PIT = get_img_data_uri("pit.png", 44)
IMG_GOLD = get_img_data_uri("gold.png", 44)
IMG_BREEZE = get_img_data_uri("breeze.png", 36)
IMG_STENCH = get_img_data_uri("stench.png", 36)

# ---------- Model ----------
class Cell:
    def __init__(self):
        self.pit = False
        self.wumpus = False
        self.gold = False
        self.breeze = False
        self.stench = False
        self.glitter = False

def create_world(grid_size, start_pos):
    grid = [[Cell() for _ in range(grid_size)] for _ in range(grid_size)]

    def place_random(exclude, count=1, forbid=set()):
        positions = [(i, j) for i in range(grid_size) for j in range(grid_size)
                     if (i, j) != exclude and (i, j) not in forbid]
        if count <= 0:
            return []
        count = min(count, len(positions))
        return random.sample(positions, count)

    wumpus_pos = place_random(start_pos, 1)[0]
    forbid = {wumpus_pos, start_pos}
    gold_pos = place_random(start_pos, 1, forbid=forbid)[0]
    forbid.add(gold_pos)

    pit_count = max(1, grid_size // 2)
    pit_positions = place_random(start_pos, pit_count, forbid=forbid)
    # ensure enough pits if forbids reduced choices
    if len(pit_positions) < pit_count:
        remaining = pit_count - len(pit_positions)
        extra = place_random(start_pos, remaining, forbid={start_pos})
        pit_positions += [p for p in extra if p not in forbid]

    grid[wumpus_pos[0]][wumpus_pos[1]].wumpus = True
    grid[gold_pos[0]][gold_pos[1]].gold = True
    for x, y in pit_positions:
        grid[x][y].pit = True

    def add_adjacent_effect(x, y, attr):
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid_size and 0 <= ny < grid_size:
                setattr(grid[nx][ny], attr, True)

    add_adjacent_effect(*wumpus_pos, 'stench')
    add_adjacent_effect(*gold_pos, 'glitter')
    for x, y in pit_positions:
        add_adjacent_effect(x, y, 'breeze')

    return grid, wumpus_pos, gold_pos, pit_positions

def bfs_path(grid, start, goal, avoid_wumpus=True):
    if start == goal:
        return [start]
    grid_size = len(grid)
    q = deque([start])
    visited = {start: None}
    while q:
        cur = q.popleft()
        if cur == goal:
            path = []
            node = cur
            while node is not None:
                path.append(node)
                node = visited[node]
            path.reverse()
            return path
        x, y = cur
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = x+dx, y+dy
            if 0 <= nx < grid_size and 0 <= ny < grid_size:
                if (nx, ny) in visited:
                    continue
                cell = grid[nx][ny]
                blocked = cell.pit or (avoid_wumpus and cell.wumpus)
                if not blocked:
                    visited[(nx,ny)] = cur
                    q.append((nx,ny))
    return None

# ---------- Utility describers ----------
def describe_cell(grid, pos, collected):
    x, y = pos
    cell = grid[x][y]
    contents = []
    if cell.gold and not collected:
        contents.append("Gold")
    if cell.wumpus:
        contents.append("Wumpus")
    if cell.pit:
        contents.append("Pit")
    if not contents:
        contents.append("Safe")
    return ", ".join(contents)

def describe_percepts(grid, pos):
    x, y = pos
    cell = grid[x][y]
    p = []
    if cell.breeze:
        p.append("Breeze")
    if cell.stench:
        p.append("Stench")
    if cell.glitter:
        p.append("Glitter")
    if not p:
        return "None"
    return ", ".join(p)

# ---------- Session initialization ----------
def reset_session(grid_size):
    start_pos = (0, 0)
    grid, wumpus_pos, gold_pos, pit_positions = create_world(grid_size, start_pos)
    initial_entry = {
        'step': 0,
        'pos': start_pos,
        'cell_contents': describe_cell(grid, start_pos, collected=False),
        'percepts': describe_percepts(grid, start_pos),
        'score': 0,
        'event': 'Start'
    }
    st.session_state.update({
        'grid': grid,
        'grid_size': grid_size,
        'wumpus_pos': wumpus_pos,
        'gold_pos': gold_pos,
        'pit_positions': pit_positions,
        'agent_pos': start_pos,
        'direction': 0,
        'score': 0,
        'arrow_used': False,
        'gold_collected': False,
        'gold_collected_at_step': None,
        'path_taken_to_gold': None,
        'game_over': False,
        'returning': False,
        'return_path': None,
        'return_index': 0,
        'playing': False,
        'paused': False,
        'stopped': False,
        'path_to_goal': None,
        'path_index': 0,
        'movement_log': [initial_entry],
        'move_count': 0,
        'visited': {start_pos},           # start visited
        'start_time': time.time(),
        'end_time': None,
        'end_reason': None
    })

# ---------- UI & Layout (styles) ----------
st.set_page_config(layout="wide", page_title="WUMPUS WORLD", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root{ --page-bg:#070710; --accent:#7c3aed; --accent2:#06b6d4; --text:#f8fafc; --muted:#9ca3af; }
html, body, .stApp { background: linear-gradient(180deg, #05040b 0%, #0b1020 100%) !important; color: var(--text); }
.block-container { padding: 8px 20px 40px 20px !important; }
.header-wrap { display:flex; justify-content:center; margin-top:28px; margin-bottom:20px; }
.title { font-size:38px; font-weight:900; color:#ffffff; text-transform:uppercase; letter-spacing:2px; text-shadow:0 0 15px #0b5fff; }
.left { display:flex; flex-direction:column; align-items:center; }
.board { display:grid; gap:10px; justify-content:center; margin: 6px 0; }
.cell { width:76px; height:76px; font-size:0; display:flex; align-items:center; justify-content:center; border-radius:10px; color:#fff; border:1px solid rgba(255,255,255,0.04); box-shadow: inset 0 -6px 12px rgba(0,0,0,0.3); padding:4px; box-sizing:border-box; }
.cell.visited { background: linear-gradient(180deg,#16a34a,#10b981); }
.cell.unvisited { background: linear-gradient(180deg,#ffe4e6,#ffd6d6); }
.cell.gold { background: linear-gradient(180deg,#ffd54a,#ffb300); }
.cell.wumpus { background: linear-gradient(180deg,#ff6b6b,#ff3b3b); }
.cell.pit { background: linear-gradient(180deg,#374151,#1f2937); }
.cell.start { box-shadow: 0 0 0 3px rgba(16,185,129,0.12); }
.cell.path { outline: 3px dashed rgba(255,255,255,0.10); }
.cell img { max-width:68px; max-height:68px; }
.agent { animation: pulse 1s infinite; }
@keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }

.controls { display:flex; gap:10px; align-items:center; margin: 8px 0 14px 0; }
.legend { display:flex; gap:8px; margin-top:10px; }
.legend .item { display:flex; gap:6px; align-items:center; font-weight:700; color:var(--text); }
.legend .box { width:18px; height:18px; border-radius:4px; display:inline-block; }

.card { border-radius:10px; padding:12px; background: rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.03); }
.card.game-summary { margin-top:18px; width:75%; color:var(--text); font-weight:700; }
.card.log { max-height:620px; overflow:auto; width:100%; }
.log-entry { border-bottom:1px dashed rgba(255,255,255,0.03); padding:8px 6px; font-weight:700; color:var(--text); }

.sidebar .stButton>button { background: linear-gradient(90deg,var(--accent),var(--accent2)); color:#fff; }

@media (max-width:1100px){ .card.game-summary{ width:95%; } .cell{ width:64px; height:64px; } .cell img { max-width:56px; max-height:56px; } }
</style>
""", unsafe_allow_html=True)

# Centered Title above grid
st.markdown("""
<div class='header-wrap'>
  <div class='title'>WUMPUS WORLD</div>
</div>
""", unsafe_allow_html=True)

# Sidebar controls
st.sidebar.header("World Settings & Tools")
chosen_size = st.sidebar.slider("Grid size", MIN_GRID, MAX_GRID, DEFAULT_GRID)
show_path_overlay = st.sidebar.checkbox("Show planned path overlay", value=True)
reveal_map = st.sidebar.checkbox("Reveal full map (cheat)", value=True)
show_coords = st.sidebar.checkbox("Show cell coordinates", value=False)
show_percepts = st.sidebar.checkbox("Show percept icons", value=True)

# Buttons in requested order
start_btn = st.sidebar.button("▶ Start")
pause_btn = st.sidebar.button("⏸ Pause/Resume")
stop_btn = st.sidebar.button("■ Stop")
reset_btn = st.sidebar.button("↺ Reset World")
download_log = st.sidebar.button("⬇️ Export Log CSV")

# Initialize or resize session
if 'grid' not in st.session_state or st.session_state.get('grid_size') != chosen_size:
    reset_session(chosen_size)

# Buttons & helpers
if reset_btn:
    reset_session(chosen_size)
    st.sidebar.success("World reset.")
if download_log:
    # prepare CSV download
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["step","pos_x","pos_y","cell_contents","percepts","score","event"])
    for e in st.session_state.movement_log:
        writer.writerow([e['step'], e['pos'][0], e['pos'][1], e['cell_contents'], e['percepts'], e['score'], e.get('event','')])
    st.download_button(label="Download log as CSV", data=buffer.getvalue(), file_name="wumpus_log.csv", mime="text/csv")

# Start / pause / stop controls behavior
if start_btn:
    st.session_state.paused = False
    st.session_state.stopped = False
    st.session_state.playing = True
    if not st.session_state.gold_collected and not st.session_state.path_to_goal:
        p = bfs_path(st.session_state.grid, st.session_state.agent_pos, st.session_state.gold_pos)
        st.session_state.path_to_goal = p
        st.session_state.path_index = 0
        if p is None:
            st.warning("No safe path to gold.")
if pause_btn:
    st.session_state.paused = not st.session_state.paused
    st.sidebar.success("Paused" if st.session_state.paused else "Resumed")
if stop_btn:
    if st.session_state.playing and not st.session_state.game_over:
        st.session_state.end_time = time.time()
        st.session_state.end_reason = 'Stopped by user'
    st.session_state.playing = False
    st.session_state.returning = False
    st.session_state.path_to_goal = None
    st.session_state.path_index = 0
    st.session_state.stopped = True
    st.sidebar.info("Stopped.")

# ---------- Rendering helpers ----------
def render_board_html(grid, agent_pos, visited_set, show_path=False, reveal=False, coords=False, percepts_on=True):
    n = len(grid)
    board_html = ""
    # build a set for path cells
    path_cells = set()
    if show_path and st.session_state.get('path_taken_to_gold'):
        path_cells = set(st.session_state['path_taken_to_gold'])
    # render rows top->bottom visually by iterating reversed y (so grid origin (0,0) bottom-left)
    for i in range(n-1, -1, -1):
        for j in range(n):
            cell = grid[i][j]
            classes = ['cell']
            inner = ''
            # whether cell features are visible
            cell_visible = reveal or (i, j) in visited_set
            # choose images / inner markup
            if cell.gold and not st.session_state.gold_collected and (cell_visible or reveal):
                classes.append('gold')
                inner = IMG_GOLD or "G"
            elif cell.wumpus and (cell_visible or reveal):
                classes.append('wumpus')
                inner = IMG_WUMPUS or "W"
            elif cell.pit and (cell_visible or reveal):
                classes.append('pit')
                inner = IMG_PIT or "P"
            else:
                if (i, j) in visited_set:
                    classes.append('visited')
                else:
                    classes.append('unvisited')
                if percepts_on and cell.stench:
                    inner = IMG_STENCH or "S"
                elif percepts_on and cell.breeze:
                    inner = IMG_BREEZE or "B"
            if (i, j) == agent_pos:
                # agent visible regardless of reveal/visited
                classes.append('visited')
                classes.append('agent')
                inner = IMG_AGENT or "A"
            if (i, j) == (0, 0):
                classes.append('start')
            if (i, j) in path_cells:
                classes.append('path')
            coord_html = f"<div style='font-size:10px; position:absolute; bottom:4px; right:4px; color:rgba(255,255,255,0.6)'>{i},{j}</div>" if coords else ""
            board_html += f"<div style='position:relative' class=\"{' '.join(classes)}\">{inner}{coord_html}</div>"
    style = f"display:grid; grid-template-columns: repeat({n}, 76px); justify-content:center;"
    return f"<div class='board' style='{style}'>{board_html}</div>"

def render_log_html(movement_log):
    html = "<div class='card log'>"
    for entry in movement_log:
        step = entry['step']; pos = entry['pos']; contents = entry['cell_contents']
        percepts = entry['percepts']; score = entry['score']; event = entry.get('event','')
        html += (
            f"<div class='log-entry'><strong>Step {step}</strong> — Pos: ({pos[0]}, {pos[1]})<br>"
            f"<small>Contents: {contents} | Percepts: {percepts}</small><br>"
            f"<small>Score: {score} {'| ' + event if event else ''}</small></div>"
        )
    html += "</div>"
    return html

def build_game_summary():
    total_moves = st.session_state.get('move_count', 0)
    final_score = st.session_state.get('score', 0)
    gold_collected = st.session_state.get('gold_collected', False)
    gold_step = st.session_state.get('gold_collected_at_step')
    path_to_gold = st.session_state.get('path_taken_to_gold')
    end_reason = st.session_state.get('end_reason')
    start_time = st.session_state.get('start_time')
    end_time = st.session_state.get('end_time')
    elapsed = None
    if start_time and end_time:
        elapsed = end_time - start_time

    summary = {
        "Gold collected": "Yes" if gold_collected else "No",
        "Gold collected at step": gold_step if gold_step is not None else "N/A",
        "Path taken to gold": " -> ".join(f"({x},{y})" for x,y in path_to_gold) if path_to_gold else "N/A",
        "Steps to collect gold": (len(path_to_gold)-1) if path_to_gold else "N/A",
        "Total moves": total_moves,
        "Final score": final_score,
        "End reason": end_reason or ("Not finished"),
        "Elapsed time (s)": f"{elapsed:.2f}" if elapsed is not None else "N/A"
    }
    html = "<div class='card game-summary'>"
    html += "<strong style='font-size:18px'>Game Summary</strong><br><br>"
    for k, v in summary.items():
        html += f"<strong>{k}:</strong> {v}<br>"
    html += "</div>"
    return html

# ---------- Layout and placeholders ----------
left_col, right_col = st.columns([3, 1])  # grid left (centered), tracker right

with left_col:
    grid_card_ph = st.empty()
    controls_ph = st.empty()
    summary_ph = st.empty()
with right_col:
    log_ph = st.empty()

# Controls under grid (static text)
controls_html = """
<div class='controls'>
  <div class='card'>
    <strong>Controls</strong> — Use the sidebar to start / pause / reset. Play speed is fixed to 1s.
  </div>
</div>
"""
controls_ph.markdown(controls_html, unsafe_allow_html=True)

# Legend
legend_html = f"""
<div class='legend card'>
  <div class='item'><div class='box' style='background:linear-gradient(180deg,#16a34a,#10b981)'></div> Visited</div>
  <div class='item'><div class='box' style='background:linear-gradient(180deg,#ffe4e6,#ffd6d6)'></div> Unvisited</div>
  <div class='item'><div class='box' style='background:linear-gradient(180deg,#ffd54a,#ffb300)'></div> Gold</div>
  <div class='item'><div class='box' style='background:linear-gradient(180deg,#ff6b6b,#ff3b3b)'></div> Wumpus</div>
  <div class='item'><div class='box' style='background:linear-gradient(180deg,#374151,#1f2937)'></div> Pit</div>
</div>
"""

# Initial render (grid centered)
board_html = render_board_html(st.session_state.grid, st.session_state.agent_pos, st.session_state.visited,
                              show_path=show_path_overlay, reveal=reveal_map, coords=show_coords, percepts_on=show_percepts)
full_html = f"<div class='left'>{board_html}{legend_html}</div>"
grid_card_ph.markdown(full_html, unsafe_allow_html=True)

# Show summary only after game over
if st.session_state.get('game_over'):
    summary_ph.markdown(build_game_summary(), unsafe_allow_html=True)
else:
    summary_ph.markdown("", unsafe_allow_html=True)

log_ph.markdown(render_log_html(st.session_state.movement_log), unsafe_allow_html=True)

# ---------- Animation / Simulation Loop ----------
def do_simulation_tick():
    moved_local = False
    # Move toward gold
    if not st.session_state.gold_collected and st.session_state.path_to_goal:
        p = st.session_state.path_to_goal; idx = st.session_state.path_index
        if idx >= len(p):
            st.session_state.path_index = max(0, len(p) - 1); idx = st.session_state.path_index
        if st.session_state.path_index < len(p) - 1:
            st.session_state.path_index += 1
            next_pos = st.session_state.path_to_goal[st.session_state.path_index]
            st.session_state.agent_pos = next_pos
            st.session_state.visited.add(next_pos)
            st.session_state.score -= 1
            st.session_state.move_count += 1
            moved_local = True

            cell = st.session_state.grid[next_pos[0]][next_pos[1]]
            event = ''
            if cell.gold and not st.session_state.gold_collected:
                st.session_state.gold_collected = True
                st.session_state.gold_collected_at_step = st.session_state.move_count
                if st.session_state.path_to_goal:
                    st.session_state.path_taken_to_gold = list(st.session_state.path_to_goal[:st.session_state.path_index + 1])
                else:
                    st.session_state.path_taken_to_gold = [next_pos]
                st.session_state.score += 1000
                st.session_state.returning = True
                st.session_state.return_path = bfs_path(st.session_state.grid, next_pos, RETURN_POS)
                st.session_state.return_index = 0
                event = 'Collected gold'
            if cell.pit or cell.wumpus:
                st.session_state.score -= 1000
                st.session_state.game_over = True
                st.session_state.end_time = time.time()
                st.session_state.end_reason = 'Died (pit/wumpus)'
                event = 'Agent died'

            entry = {
                'step': st.session_state.move_count,
                'pos': next_pos,
                'cell_contents': describe_cell(st.session_state.grid, next_pos, st.session_state.gold_collected),
                'percepts': describe_percepts(st.session_state.grid, next_pos),
                'score': st.session_state.score,
                'event': event or ''
            }
            st.session_state.movement_log.append(entry)

    # Returning after gold
    elif st.session_state.gold_collected and st.session_state.return_path:
        rp = st.session_state.return_path; ridx = st.session_state.return_index
        if ridx >= len(rp):
            st.session_state.return_index = max(0, len(rp) - 1); ridx = st.session_state.return_index
        if st.session_state.return_index < len(rp) - 1:
            st.session_state.return_index += 1
            next_pos = st.session_state.return_path[st.session_state.return_index]
            st.session_state.agent_pos = next_pos
            st.session_state.visited.add(next_pos)
            st.session_state.score -= 1
            st.session_state.move_count += 1
            moved_local = True

            cell = st.session_state.grid[next_pos[0]][next_pos[1]]
            event = ''
            if cell.pit or cell.wumpus:
                st.session_state.score -= 1000
                st.session_state.game_over = True
                st.session_state.end_time = time.time()
                st.session_state.end_reason = 'Died while returning'
                event = 'Agent died while returning'
            if next_pos == RETURN_POS and st.session_state.gold_collected:
                event = 'Returned to start with gold'
                st.session_state.playing = False
                st.session_state.returning = False
                st.session_state.return_path = None
                st.session_state.end_time = time.time()
                st.session_state.end_reason = 'Returned with gold'
                st.session_state.game_over = True  # ensure summary shows

            entry = {
                'step': st.session_state.move_count,
                'pos': next_pos,
                'cell_contents': describe_cell(st.session_state.grid, next_pos, st.session_state.gold_collected),
                'percepts': describe_percepts(st.session_state.grid, next_pos),
                'score': st.session_state.score,
                'event': event or ''
            }
            st.session_state.movement_log.append(entry)

    # Plan paths if needed
    elif st.session_state.playing and not st.session_state.gold_collected and not st.session_state.path_to_goal:
        p = bfs_path(st.session_state.grid, st.session_state.agent_pos, st.session_state.gold_pos)
        st.session_state.path_to_goal = p; st.session_state.path_index = 0
        if p is None:
            st.warning("No safe path to gold.")
    elif st.session_state.playing and st.session_state.gold_collected and not st.session_state.return_path:
        rp = bfs_path(st.session_state.grid, st.session_state.agent_pos, RETURN_POS)
        st.session_state.return_path = rp; st.session_state.return_index = 0
        if rp is None:
            st.warning("No safe return path.")

    # update the UI preview areas
    board_html_local = render_board_html(st.session_state.grid, st.session_state.agent_pos, st.session_state.visited,
                                        show_path=show_path_overlay, reveal=reveal_map, coords=show_coords, percepts_on=show_percepts)
    full_html_local = f"<div class='left'>{board_html_local}{legend_html}</div>"
    grid_card_ph.markdown(full_html_local, unsafe_allow_html=True)
    log_ph.markdown(render_log_html(st.session_state.movement_log), unsafe_allow_html=True)
    if st.session_state.get('game_over'):
        summary_ph.markdown(build_game_summary(), unsafe_allow_html=True)
    else:
        summary_ph.markdown("", unsafe_allow_html=True)

    return moved_local

# Drive the simulation (autoplay in-process — avoids full reruns and blinking)
if st.session_state.playing and not st.session_state.paused and not st.session_state.game_over:
    # run the simulation loop in the same script execution and update placeholders each tick
    while st.session_state.playing and not st.session_state.paused and not st.session_state.game_over:
        moved_flag = do_simulation_tick()
        # small sleep (fixed MOVE_DELAY) between ticks
        time.sleep(MOVE_DELAY)
        # loop will continue and update placeholders in-place; no st.experimental_rerun()
    # when loop exits (paused/stopped/game_over), the script continues to final rendering

# Re-render final state (if nothing changed) so UI shows latest
board_html = render_board_html(st.session_state.grid, st.session_state.agent_pos, st.session_state.visited,
                              show_path=show_path_overlay, reveal=reveal_map, coords=show_coords, percepts_on=show_percepts)
full_html = f"<div class='left'>{board_html}{legend_html}</div>"
grid_card_ph.markdown(full_html, unsafe_allow_html=True)
log_ph.markdown(render_log_html(st.session_state.movement_log), unsafe_allow_html=True)
if st.session_state.get('game_over'):
    summary_ph.markdown(build_game_summary(), unsafe_allow_html=True)
else:
    summary_ph.markdown("", unsafe_allow_html=True)