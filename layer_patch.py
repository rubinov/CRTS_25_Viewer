import re

with open('CRTS_25_viewer.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update __init__ filter criteria
code = re.sub(
    r'self\.hist_filter_min_b0 = 0\n.*?self\.hist_filter_threshold = 0',
    '''self.hist_filter_min_layers = [0] * 6
        self.hist_filter_threshold = 0''',
    code, flags=re.DOTALL
)

code = re.sub(
    r'self\.min_hits_board0 = tk\.IntVar\(value=0\)\n.*?self\.min_hits_board2 = tk\.IntVar\(value=0\)',
    'self.min_hits_layers = [tk.IntVar(value=0) for _ in range(6)]',
    code, flags=re.DOTALL
)

# 2. Update create_widgets filter UI
ui_old = '''        tk.Label(filter_frame, text="Min Hits Board 0:", bg='#2C3E50', fg='white',
                font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=5)

        tk.Spinbox(filter_frame, from_=0, to=64, textvariable=self.min_hits_board0,
                  width=5, font=('Arial', 11)).pack(side=tk.LEFT, padx=5)

        tk.Label(filter_frame, text="Min Hits Board 1:", bg='#2C3E50', fg='white',
                font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=15)

        tk.Spinbox(filter_frame, from_=0, to=64, textvariable=self.min_hits_board1,
                  width=5, font=('Arial', 11)).pack(side=tk.LEFT, padx=5)

        tk.Label(filter_frame, text="Min Hits Board 2:", bg='#2C3E50', fg='white',
                font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=15)

        tk.Spinbox(filter_frame, from_=0, to=64, textvariable=self.min_hits_board2,
                  width=5, font=('Arial', 11)).pack(side=tk.LEFT, padx=5)

        tk.Label(filter_frame, text="HG Threshold:", bg='#2C3E50', fg='white',
                font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=15)'''

ui_new = '''        for i in range(6):
            tk.Label(filter_frame, text=f"L{i}:", bg='#2C3E50', fg='white',
                    font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(10 if i==0 else 5, 2))
            tk.Spinbox(filter_frame, from_=0, to=64, textvariable=self.min_hits_layers[i],
                      width=3, font=('Arial', 10)).pack(side=tk.LEFT, padx=0)

        tk.Label(filter_frame, text="HG Thresh:", bg='#2C3E50', fg='white',
                font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(15, 2))'''

code = code.replace(ui_old, ui_new)

# 3. Update apply_filter & update_load_status
af_old = '''    def apply_filter(self):
        """Filter events based on minimum hit criteria and update display for threshold changes"""
        if not self.paired_events:
            messagebox.showwarning("Warning", "No events loaded")
            return

        min_b0 = self.min_hits_board0.get()
        min_b1 = self.min_hits_board1.get()
        min_b2 = self.min_hits_board2.get()
        hg_thresh = self.hg_threshold.get()

        self.filtered_events = self._filter_paired_events(
            self.paired_events, min_b0, min_b1, hg_thresh, min_b2
        )

        if not self.filtered_events:
            messagebox.showwarning("Warning",
                                 f"No events match criteria:\\n"
                                 f"Board 0 >= {min_b0} hits\\n"
                                 f"Board 1 >= {min_b1} hits\\n"
                                 f"Board 2 >= {min_b2} hits")
            self.filtered_events = self.paired_events  # Reset to all
            self.filter_status.config(text="Showing all events (no matches)")
            return

        self.current_event_idx = 0
        self.update_display()
        self._update_load_status()'''

af_new = '''    def apply_filter(self):
        """Filter events based on minimum hit criteria and update display for threshold changes"""
        if not self.paired_events:
            messagebox.showwarning("Warning", "No events loaded")
            return

        min_layers = [var.get() for var in self.min_hits_layers]
        hg_thresh = self.hg_threshold.get()

        self.filtered_events = self._filter_paired_events(
            self.paired_events, min_layers, hg_thresh
        )

        if not self.filtered_events:
            msg = "No events match criteria:\\n"
            for i, min_h in enumerate(min_layers):
                if min_h > 0: msg += f"Layer {i} >= {min_h} hits\\n"
            if len(msg.splitlines()) == 1: msg = "No events match criteria."

            messagebox.showwarning("Warning", msg)
            self.filtered_events = self.paired_events  # Reset to all
            self.filter_status.config(text="Showing all events (no matches)")
            return

        self.current_event_idx = 0
        self.update_display()
        self._update_load_status()'''

code = code.replace(af_old, af_new)

code = re.sub(
    r'    def _update_load_status\(self\):.*?            else:\n                self\.filter_status\.config\(text=f"Filtered: \{desc\} \(loading\.\.\.\)"\)',
    '''    def _update_load_status(self):
        """Refresh the filter_status label."""
        min_layers = [var.get() for var in self.min_hits_layers]

        if all(x == 0 for x in min_layers):
            if self.all_events_loaded:
                self.filter_status.config(text="Showing all events")
            else:
                self.filter_status.config(text="Showing all available events (loading...)")
        else:
            conds = [f"L{i}>={m}" for i, m in enumerate(min_layers) if m > 0]
            desc = " & ".join(conds)
            
            if self.all_events_loaded:
                self.filter_status.config(text=f"Filtered: {desc}")
            else:
                self.filter_status.config(text=f"Filtered: {desc} (loading...)")''',
    code, flags=re.DOTALL
)

# 4. _filter_paired_events
fpe_old = re.search(r'    def _filter_paired_events\(self, paired_events.*?\n\n', code, flags=re.DOTALL).group(0)
fpe_new = '''    def _filter_paired_events(self, paired_events, min_layers, threshold):
        """Helper to filter paired events by hit counts per layer and threshold"""
        filtered = []

        for pair in paired_events:
            layer_hits = [0] * 6
            for b_name, b_map in [('board0', self.board0_map), ('board1', self.board1_map), ('board2', self.board2_map)]:
                evt = pair.get(b_name)
                if not evt: continue
                
                for hit in evt.hits:
                    if self.data_mode == "SPECT_TIMING":
                        if getattr(hit, 'energy_hg', None) is None or hit.energy_hg <= threshold:
                            continue
                            
                    ch = hit.channel
                    pos = b_map.get(ch)
                    if pos:
                        layer = pos[0]
                        if 0 <= layer < 6:
                            layer_hits[layer] += 1
            
            passes = True
            for L in range(6):
                if layer_hits[L] < min_layers[L]:
                    passes = False
                    break
            
            if passes:
                filtered.append(pair)

        return filtered\n\n'''
code = code.replace(fpe_old, fpe_new)

# 5. Background re-filter (forward nav trigger)
code = re.sub(
    r'        min_b0 = self\.min_hits_board0\.get\(\)\n.*?self\.paired_events, min_b0, min_b1, threshold, min_b2\n        \)',
    '''        min_layers = [var.get() for var in self.min_hits_layers]
        threshold = self.hg_threshold.get()
        new_filtered = self._filter_paired_events(
            self.paired_events, min_layers, threshold
        )''',
    code, flags=re.DOTALL
)

# 6. check_for_new_events (watch mode target)
code = re.sub(
    r'                min_b0 = self\.min_hits_board0\.get\(\)\n.*?self\.paired_events, min_b0, min_b1, threshold, min_b2\n                \)',
    '''                min_layers = [var.get() for var in self.min_hits_layers]
                threshold = self.hg_threshold.get()

                self.filtered_events = self._filter_paired_events(
                    self.paired_events, min_layers, threshold
                )''',
    code, flags=re.DOTALL
)

# 7. toggle_histogram_task
code = re.sub(
    r'        self\.hist_filter_min_b0 = self\.min_hits_board0\.get\(\)\n.*?self\.hist_filter_threshold = self\.hg_threshold\.get\(\)',
    '''        self.hist_filter_min_layers = [var.get() for var in self.min_hits_layers]
        self.hist_filter_threshold = self.hg_threshold.get()''',
    code, flags=re.DOTALL
)

# 8. histogram_worker filtering
hw_f1 = '''        min_b0    = self.hist_filter_min_b0
        min_b1    = self.hist_filter_min_b1
        min_b2    = self.hist_filter_min_b2
        threshold = self.hist_filter_threshold'''
hw_f2 = '''        min_layers = self.hist_filter_min_layers
        threshold  = self.hist_filter_threshold'''
code = code.replace(hw_f1, hw_f2)

code = code.replace(
    '        filtered_pairs = self._filter_paired_events(pairs, min_b0, min_b1, threshold, min_b2)',
    '        filtered_pairs = self._filter_paired_events(pairs, min_layers, threshold)'
)

hw_dict_old = '''            'filter_params': {
                'min_hits_board0': min_b0,
                'min_hits_board1': min_b1,
                'min_hits_board2': min_b2,
                'hg_threshold':    threshold,
            },'''
hw_dict_new = '''            'filter_params': {
                'min_hits_layers': min_layers,
                'hg_threshold':    threshold,
            },'''
code = code.replace(hw_dict_old, hw_dict_new)

# 9. save_histograms_hdf5 filter param writer
h5_old = '''                fp = self.hist_data['filter_params']
                fgrp.attrs['min_hits_board0'] = fp['min_hits_board0']
                fgrp.attrs['min_hits_board1'] = fp['min_hits_board1']
                fgrp.attrs['min_hits_board2'] = fp['min_hits_board2']
                fgrp.attrs['hg_threshold']    = fp['hg_threshold']'''
h5_new = '''                fp = self.hist_data['filter_params']
                fgrp.attrs['min_hits_layers'] = fp['min_hits_layers']
                fgrp.attrs['hg_threshold']    = fp['hg_threshold']'''
code = code.replace(h5_old, h5_new)


with open('CRTS_25_viewer.py', 'w', encoding='utf-8') as f:
    f.write(code)
