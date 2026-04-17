import os

with open('CRTS_25_viewer.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Replace __init__ section
code = code.replace('''        self.color_hit = "#E74C3C"     # Red

        # Load board 2 strip mapping before building widgets (cells created in create_widgets)
        self.board2_strip = self._load_board2_strip()

        # Create GUI
        self.create_widgets()

        # Load default mapping files if they exist
        self.load_mapping_file("CRTS_new_25_mapping_board0.txt", 0)
        self.load_mapping_file("CRTS_new_25_mapping_board1.txt", 1)

    def create_widgets(self):''',
'''        self.color_hit = "#E74C3C"     # Red

        self.board0_map = self.load_combined_mapping("CRTS_new_25_mapping_board0.txt") or self._default_map(1)
        self.board1_map = self.load_combined_mapping("CRTS_new_25_mapping_board1.txt") or self._default_map(1)
        self.board2_map = self.load_combined_mapping("CRTS_new_25_mapping_board2.txt") or {}

        # Combine maps for Top/Bot halves
        self.top_half_map_b0 = self.board0_map
        self.top_half_map_b2 = self.board2_map
        
        self.bot_half_map_b1 = self.board1_map
        self.bot_half_map_b2 = self.board2_map

        # Create GUI
        self.create_widgets()

    def _default_map(self, row_offset):
        m = {}
        for ch in range(64):
            m[ch] = (row_offset + (ch // 16), ch % 16)
        return m

    def load_combined_mapping(self, filename):
        candidates = [
            os.path.join(os.path.dirname(__file__), filename),
            os.path.join(os.getcwd(), filename),
            os.path.join(os.path.dirname(__file__), filename.replace('CRTS_new_25_mapping_', 'CTS_mapping_')),
        ]
        mapping = {}
        loaded_path = None
        for path in candidates:
            try:
                with open(path, 'r') as f:
                    lines = [l.strip() for l in f if l.strip()]
                for line in lines:
                    if ':' not in line: continue
                    parts = line.split(':')
                    r = int(parts[0].strip())
                    chs_str = parts[1].strip()
                    if not chs_str: continue
                    chs = [int(x.strip()) for x in chs_str.split(',')]
                    start_col = (16 - len(chs)) // 2
                    for col_offset, ch in enumerate(chs):
                        mapping[ch] = (r, start_col + col_offset)
                loaded_path = path
                break
            except Exception:
                continue

        if mapping:
            print(f"Loaded mapping from {loaded_path}")
        else:
            print(f"Warning: Could not load mapping for {filename}")
        return mapping

    def create_widgets(self):''')

# 2. Replace widget creation section
start_mark = '# Main display area'
end_mark = '    def _load_board2_strip(self):'
idx1 = code.find(start_mark)
idx2 = code.find(end_mark)

new_widgets = '''# Main display area
        display_frame = tk.Frame(self.root, bg='#ECF0F1')
        display_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── Top Half (Board 0 + Board 2) ──────────────────────────────────
        board0_frame = tk.Frame(display_frame, bg='#ECF0F1')
        board0_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False, pady=0)

        b0_header = tk.Frame(board0_frame, bg='#ECF0F1')
        b0_header.pack(side=tk.TOP, fill=tk.X, pady=(2, 2))
        tk.Label(b0_header, text="Board 0 & 2", bg='#ECF0F1', fg='#2C3E50',
                font=('Arial', 16, 'bold'), width=10, anchor='w'
                ).pack(side=tk.LEFT, padx=(10, 5))

        self.top_cells = self.create_half_grid(board0_frame, self.top_half_map_b0, self.top_half_map_b2)

        # ── Separator ───────────────────────────────────────────────────
        import tkinter.ttk as ttk
        ttk.Separator(display_frame, orient='horizontal').pack(fill=tk.X, pady=6)

        # ── Bottom Half (Board 1 + Board 2) ─────────────────────────────
        board1_frame = tk.Frame(display_frame, bg='#ECF0F1')
        board1_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False, pady=0)

        b1_header = tk.Frame(board1_frame, bg='#ECF0F1')
        b1_header.pack(side=tk.TOP, fill=tk.X, pady=(2, 2))
        tk.Label(b1_header, text="Board 1 & 2", bg='#ECF0F1', fg='#2C3E50',
                font=('Arial', 16, 'bold'), width=10, anchor='w'
                ).pack(side=tk.LEFT, padx=(10, 5))

        self.bot_cells = self.create_half_grid(board1_frame, self.bot_half_map_b1, self.bot_half_map_b2)

    def create_half_grid(self, parent, map_primary, map_b2):
        grid_frame = tk.Frame(parent, bg='#ECF0F1')
        grid_frame.pack(expand=True)
        cells = {}
        positions = set(map_primary.values()) | set(map_b2.values())
        
        for r, c in positions:
            cell = tk.Label(grid_frame, text="", bg=self.color_no_hit,
                          fg='white', font=('Courier', 9, 'bold'),
                          width=10, height=3,
                          relief=tk.RAISED, bd=1,
                          justify=tk.CENTER)
            cell.grid(row=r, column=c, padx=1, pady=0)
            cells[(r, c)] = cell
        return cells

'''
code = code[:idx1] + new_widgets + code[idx2:]

# 3. Delete old parsers _load_board2_strip, _create_strip_row, load_mapping_file
start_mark = '    def _load_board2_strip(self):'
end_mark = '    def load_data_file(self):'
idx1 = code.find(start_mark)
idx2 = code.find(end_mark)
code = code[:idx1] + code[idx2:]

# 4. Modify update_display clearing logic
update_old = '''        # Clear all cells
        for cells in [self.board0_cells, self.board1_cells]:
            for cell in cells.values():
                cell.config(text="", bg=self.color_no_hit)
                
        # Clear strip cells
        if hasattr(self, 'board2_strip_cells_top'):
            for cell in self.board2_strip_cells_top.values():
                cell.config(bg=self.color_no_hit)
        if hasattr(self, 'board2_strip_cells_bot'):
            for cell in self.board2_strip_cells_bot.values():
                cell.config(bg=self.color_no_hit)'''

update_new = '''        # Clear all cells to default '#CH' view
        for mapping, cells in [
            (self.top_half_map_b0, self.top_cells),
            (self.top_half_map_b2, self.top_cells),
            (self.bot_half_map_b1, self.bot_cells),
            (self.bot_half_map_b2, self.bot_cells)
        ]:
            for ch, pos in mapping.items():
                if pos in cells:
                    cells[pos].config(text=f"#{ch:02d}", bg=self.color_no_hit)'''

code = code.replace(update_old, update_new)

# 5. Modify update_display rendering logic
render_old = '''        # Board 0
        if current_pair.get('board0'):
            self.display_board_event(current_pair['board0'], 0)
            mode = f"Mode: {current_pair['board0'].meta.get('mode', 'Unknown')}"

        # Board 1
        if current_pair.get('board1'):
            self.display_board_event(current_pair['board1'], 1)
            mode = f"Mode: {current_pair['board1'].meta.get('mode', 'Unknown')}"
            
        # Board 2 (Strips)
        if hasattr(self, 'board2_strip_cells_top') and current_pair.get('board2'):
            hit_data = {hit.channel: hit for hit in current_pair['board2'].hits}
            for ch, cell in self.board2_strip_cells_top.items():
                if ch in hit_data:
                    hit = hit_data[ch]
                    line1 = f"#{ch:02d}"
                    line2, line3 = "", ""
                    if hasattr(hit, 'hg') and hasattr(hit, 'lg'): line2 = f"{hit.hg:04d}/{hit.lg:04d}"
                    if hasattr(hit, 'toa') and hasattr(hit, 'tot'): line3 = f"{hit.toa:04d}/{hit.tot:03d}"
                    cell.config(text=f"{line1}\\n{line2}\\n{line3}", bg=self.color_hit)
                else:
                    cell.config(text=f"#{ch:02d}", bg=self.color_no_hit)

        if hasattr(self, 'board2_strip_cells_bot') and current_pair.get('board2'):
            hit_data = {hit.channel: hit for hit in current_pair['board2'].hits}
            for ch, cell in self.board2_strip_cells_bot.items():
                if ch in hit_data:
                    hit = hit_data[ch]
                    line1 = f"#{ch:02d}"
                    line2, line3 = "", ""
                    if hasattr(hit, 'hg') and hasattr(hit, 'lg'): line2 = f"{hit.hg:04d}/{hit.lg:04d}"
                    if hasattr(hit, 'toa') and hasattr(hit, 'tot'): line3 = f"{hit.toa:04d}/{hit.tot:03d}"
                    cell.config(text=f"{line1}\\n{line2}\\n{line3}", bg=self.color_hit)
                else:
                    cell.config(text=f"#{ch:02d}", bg=self.color_no_hit)'''

render_new = '''        # Board 0 (Top Half)
        if current_pair.get('board0'):
            self.display_board_event(current_pair['board0'], self.top_cells, self.top_half_map_b0)
            mode = f"Mode: {current_pair['board0'].meta.get('mode', 'Unknown')}"

        # Board 1 (Bot Half)
        if current_pair.get('board1'):
            self.display_board_event(current_pair['board1'], self.bot_cells, self.bot_half_map_b1)
            mode = f"Mode: {current_pair['board1'].meta.get('mode', 'Unknown')}"
            
        # Board 2 (Both Halves)
        if current_pair.get('board2'):
            self.display_board_event(current_pair['board2'], self.top_cells, self.top_half_map_b2)
            self.display_board_event(current_pair['board2'], self.bot_cells, self.bot_half_map_b2)
            mode = f"Mode: {current_pair['board2'].meta.get('mode', 'Unknown')}"'''

code = code.replace(render_old, render_new)

# 6. Make display_board_event generic
old_dbe = '''    def display_board_event(self, event, board_id):
        """Update the UI with data from a single board event"""
        if not event: return

        cells = self.board0_cells if board_id == 0 else self.board1_cells
        mapping = self.board0_mapping if board_id == 0 else self.board1_mapping
        
        # Map channel -> hit for fast lookup
        hit_data = {hit.channel: hit for hit in event.hits}

        for ch in range(64):
            if ch not in mapping: continue
            row, col = mapping[ch]
            
            # Using tuple to access dict
            cell = cells.get((row, col))
            if not cell: continue

            if ch in hit_data:
                hit = hit_data[ch]

                line1 = f"#{ch:02d}"
                line2 = ""
                line3 = ""

                if hasattr(hit, 'hg') and hasattr(hit, 'lg'):
                    line2 = f"{hit.hg:04d}/{hit.lg:04d}"
                if hasattr(hit, 'toa') and hasattr(hit, 'tot'):
                    line3 = f"{hit.toa:04d}/{hit.tot:03d}"

                cell.config(
                    text=f"{line1}\\n{line2}\\n{line3}",
                    bg=self.color_hit
                )
            else:
                cell.config(
                    text=f"#{ch:02d}",
                    bg=self.color_no_hit
                )'''

new_dbe = '''    def display_board_event(self, event, cells_dict, mapping_dict):
        """Update the cells defined in mapping_dict with hit data from event"""
        if not event: return

        # Map channel -> hit for fast lookup
        hit_data = {hit.channel: hit for hit in event.hits}

        for ch, hit in hit_data.items():
            if ch not in mapping_dict: continue
            pos = mapping_dict[ch]
            if pos not in cells_dict: continue
            
            cell = cells_dict[pos]

            line1 = f"#{ch:02d}"
            line2 = ""
            line3 = ""

            if hasattr(hit, 'hg') and hasattr(hit, 'lg'):
                line2 = f"{hit.hg:04d}/{hit.lg:04d}"
            if hasattr(hit, 'toa') and hasattr(hit, 'tot'):
                line3 = f"{hit.toa:04d}/{hit.tot:03d}"

            cell.config(
                text=f"{line1}\\n{line2}\\n{line3}",
                bg=self.color_hit
            )'''

code = code.replace(old_dbe, new_dbe)

with open('CRTS_25_viewer.py', 'w', encoding='utf-8') as f:
    f.write(code)
