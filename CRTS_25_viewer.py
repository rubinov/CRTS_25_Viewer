#!/usr/bin/env python3
"""
Unified Event Viewer GUI for JanusC
Displays events from both TIMING and SPECTROSCOPY+TIMING mode binary files

Author: Claude (with Paul)
Started Date: 2 January 2026
Last Updated: 17 April 2026
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import os
import csv
import threading
import h5py
import numpy as np

# Ensure the directory containing this script is on sys.path so that the
# 'modules' package is found regardless of the current working directory.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from modules.unpackers.spect_t_unpacker import SpecTDataUnpacker
from modules.unpackers.realtime_unpacker import RealtimeEventUnpacker, detect_file_mode


class UnifiedEventViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Event Viewer - JanusC (Timing & SpecT)")
        self.root.geometry("1800x1100")

        # Data storage
        self.unpacker = None
        self.realtime_unpacker = None  # For watch mode
        self.raw_events = []
        self.paired_events = []  # All events grouped by timestamp
        self.filtered_events = []  # Filtered based on hit criteria
        self.current_event_idx = 0
        self.board0_mapping = None
        self.board1_mapping = None
        self.data_mode = None  # Will be "TIMING" or "SPECT_TIMING"

        # Board 2 strip (channels above Board 0 and above Board 1 displays)
        self.board2_strip = None            # [[row0_chs], [row1_chs]] from mapping file
        self.board2_strip_cells_top = {}    # ch -> Label, strip row 0 (near Board 0 header)
        self.board2_strip_cells_bot = {}    # ch -> Label, strip row 1 (near Board 1 header)

        # Chunked loading state
        self.file_data = None          # Raw bytes of the loaded file (held in memory)
        self.parse_offset = 0          # Byte offset of next unparsed event
        self.events_parse_count = 0    # Total raw events parsed so far
        self.all_events_loaded = False # True once parse_offset reaches EOF
        self.chunk_size = 100          # Events to parse per chunk
        self.load_threshold = 10       # Trigger next chunk when <=N events remain

        # Watch mode control
        self.watch_active = False
        self.watch_after_id = None  # For scheduling the polling loop

        # Loaded file path (needed for deriving histogram filename)
        self.data_filename = None

        # Save interesting events
        self.interesting_events_file = None  # CSV file path (chosen on first save)

        # Background histogram task
        self.hist_thread = None
        self.hist_running = False
        self.hist_events_read = 0
        self.hist_lock = threading.Lock()
        self.hist_data = None  # dict with 'all' and 'filtered' sub-dicts when complete
        self.hist_update_id = None  # after() id for 10-second count updates
        # Filter params captured at the moment the histogram task is launched
        self.hist_filter_min_b0 = 0
        self.hist_filter_min_b1 = 0
        self.hist_filter_min_b2 = 0
        self.hist_filter_threshold = 0

        # Filter criteria
        self.min_hits_board0 = tk.IntVar(value=0)
        self.min_hits_board1 = tk.IntVar(value=0)
        self.min_hits_board2 = tk.IntVar(value=0)
        self.hg_threshold = tk.IntVar(value=1000)  # HG threshold for SPECT_TIMING mode

        # Colors
        self.color_no_hit = "#4A90E2"  # Blue
        self.color_hit = "#E74C3C"     # Red

        # Load board 2 strip mapping before building widgets (cells created in create_widgets)
        self.board2_strip = self._load_board2_strip()

        # Create GUI
        self.create_widgets()

        # Load default mapping files if they exist
        self.load_mapping_file("C:/UMD-END/Janus-UMD/gui/CTS_mapping_board0.txt", 0)
        self.load_mapping_file("C:/UMD-END/Janus-UMD/gui/CTS_mapping_board1.txt", 1)

    def create_widgets(self):
        """Create all GUI widgets"""

        # Top control panel
        control_frame = tk.Frame(self.root, bg='#2C3E50', height=120)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        control_frame.pack_propagate(False)

        # File selection
        tk.Label(control_frame, text="Data File:", bg='#2C3E50', fg='white',
                font=('Arial', 12, 'bold')).grid(row=0, column=0, padx=10, pady=5, sticky='w')

        self.file_label = tk.Label(control_frame, text="No file loaded", bg='#34495E',
                                   fg='white', width=50, anchor='w', font=('Arial', 10))
        self.file_label.grid(row=0, column=1, padx=5, pady=5)

        tk.Button(control_frame, text="Load File", command=self.load_data_file,
                 bg='#3498DB', fg='white', font=('Arial', 10, 'bold'),
                 width=12).grid(row=0, column=2, padx=5, pady=5)

        # Mode indicator
        self.mode_label = tk.Label(control_frame, text="Mode: Unknown", bg='#34495E',
                                   fg='#F39C12', width=20, font=('Arial', 10, 'bold'))
        self.mode_label.grid(row=0, column=3, padx=5, pady=5)

        # Filter controls
        filter_frame = tk.Frame(control_frame, bg='#2C3E50')
        filter_frame.grid(row=1, column=0, columnspan=4, padx=10, pady=10, sticky='w')

        tk.Label(filter_frame, text="Min Hits Board 0:", bg='#2C3E50', fg='white',
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
                font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=15)

        tk.Spinbox(filter_frame, from_=0, to=16383, textvariable=self.hg_threshold,
                  width=6, font=('Arial', 11)).pack(side=tk.LEFT, padx=5)

        tk.Button(filter_frame, text="Apply Filter", command=self.apply_filter,
                 bg='#E67E22', fg='white', font=('Arial', 10, 'bold'),
                 width=12).pack(side=tk.LEFT, padx=20)

        self.filter_status = tk.Label(filter_frame, text="Showing all events",
                                     bg='#2C3E50', fg='#F39C12', font=('Arial', 10, 'bold'))
        self.filter_status.pack(side=tk.LEFT, padx=10)

        # Event info
        tk.Label(control_frame, text="Event:", bg='#2C3E50', fg='white',
                font=('Arial', 12, 'bold')).grid(row=2, column=0, padx=10, pady=5, sticky='w')

        self.event_info = tk.Label(control_frame, text="No events loaded", bg='#34495E',
                                   fg='white', width=50, anchor='w', font=('Arial', 10))
        self.event_info.grid(row=2, column=1, padx=5, pady=5)

        # Navigation buttons
        nav_frame = tk.Frame(control_frame, bg='#2C3E50')
        nav_frame.grid(row=2, column=2, columnspan=2, padx=5, pady=5)

        tk.Button(nav_frame, text="◄◄ First", command=self.first_event,
                 bg='#27AE60', fg='white', font=('Arial', 10, 'bold'),
                 width=10).pack(side=tk.LEFT, padx=2)

        tk.Button(nav_frame, text="◄ Prev", command=self.prev_event,
                 bg='#27AE60', fg='white', font=('Arial', 10, 'bold'),
                 width=10).pack(side=tk.LEFT, padx=2)

        tk.Button(nav_frame, text="Next ►", command=self.next_event,
                 bg='#27AE60', fg='white', font=('Arial', 10, 'bold'),
                 width=10).pack(side=tk.LEFT, padx=2)

        tk.Button(nav_frame, text="Last ►►", command=self.last_event,
                 bg='#27AE60', fg='white', font=('Arial', 10, 'bold'),
                 width=10).pack(side=tk.LEFT, padx=2)

        tk.Button(nav_frame, text="★ Save Event", command=self.save_interesting_event,
                 bg='#F39C12', fg='white', font=('Arial', 10, 'bold'),
                 width=14).pack(side=tk.LEFT, padx=15)

        self.hist_button = tk.Button(nav_frame, text="▶ Build Histograms",
                                     command=self.toggle_histogram_task,
                                     bg='#1ABC9C', fg='white', font=('Arial', 10, 'bold'),
                                     width=18)
        self.hist_button.pack(side=tk.LEFT, padx=40)

        self.hist_count_label = tk.Label(nav_frame, text="Events processed: —",
                                         bg='#2C3E50', fg='#95A5A6',
                                         font=('Arial', 10, 'bold'))
        self.hist_count_label.pack(side=tk.LEFT, padx=5)

        # Watch mode controls
        watch_frame = tk.Frame(control_frame, bg='#2C3E50')
        watch_frame.grid(row=3, column=2, columnspan=2, padx=5, pady=5, sticky='w')

        self.watch_button = tk.Button(watch_frame, text="▶ Watch File",
                                      command=self.toggle_watch_mode,
                                      bg='#9B59B6', fg='white', font=('Arial', 10, 'bold'),
                                      width=15)
        self.watch_button.pack(side=tk.LEFT, padx=5)

        self.watch_status = tk.Label(watch_frame, text="Watch: OFF", bg='#2C3E50',
                                     fg='#95A5A6', font=('Arial', 10, 'bold'))
        self.watch_status.pack(side=tk.LEFT, padx=10)

        # Main display area
        display_frame = tk.Frame(self.root, bg='#ECF0F1')
        display_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── Board 0 ────────────────────────────────────────────────────────
        board0_frame = tk.Frame(display_frame, bg='#ECF0F1')
        board0_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)

        # Header row: "Board 0" label (left) + board2 strip row 0
        b0_header = tk.Frame(board0_frame, bg='#ECF0F1')
        b0_header.pack(side=tk.TOP, fill=tk.X, pady=(5, 3))

        tk.Label(b0_header, text="Board 0", bg='#ECF0F1', fg='#2C3E50',
                font=('Arial', 16, 'bold'), width=10, anchor='w'
                ).pack(side=tk.LEFT, padx=(10, 5))

        strip_top_frame = tk.Frame(b0_header, bg='#ECF0F1')
        strip_top_frame.pack(side=tk.LEFT)
        strip0_chs = self.board2_strip[0] if self.board2_strip and len(self.board2_strip) > 0 else []
        self.board2_strip_cells_top = self._create_strip_row(strip_top_frame, strip0_chs)

        self.board0_cells = self.create_board_grid(board0_frame)

        # ── Separator (reduced padding to reclaim 8 px) ─────────────────────
        ttk.Separator(display_frame, orient='horizontal').pack(fill=tk.X, pady=6)

        # ── Board 1 ────────────────────────────────────────────────────────
        board1_frame = tk.Frame(display_frame, bg='#ECF0F1')
        board1_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)

        # Header row: "Board 1" label (left) + board2 strip row 1
        b1_header = tk.Frame(board1_frame, bg='#ECF0F1')
        b1_header.pack(side=tk.TOP, fill=tk.X, pady=(5, 3))

        tk.Label(b1_header, text="Board 1", bg='#ECF0F1', fg='#2C3E50',
                font=('Arial', 16, 'bold'), width=10, anchor='w'
                ).pack(side=tk.LEFT, padx=(10, 5))

        strip_bot_frame = tk.Frame(b1_header, bg='#ECF0F1')
        strip_bot_frame.pack(side=tk.LEFT)
        strip1_chs = self.board2_strip[1] if self.board2_strip and len(self.board2_strip) > 1 else []
        self.board2_strip_cells_bot = self._create_strip_row(strip_bot_frame, strip1_chs)

        self.board1_cells = self.create_board_grid(board1_frame)

    def create_board_grid(self, parent):
        """Create a 16x4 grid of cells for one board with 3-line display"""
        grid_frame = tk.Frame(parent, bg='#ECF0F1')
        grid_frame.pack(expand=True)

        cells = {}

        for row in range(4):
            for col in range(16):
                cell = tk.Label(grid_frame, text="", bg=self.color_no_hit,
                              fg='white', font=('Courier', 9, 'bold'),
                              width=10, height=5,
                              relief=tk.RAISED, bd=1,
                              justify=tk.CENTER)
                cell.grid(row=row, column=col, padx=1, pady=0)
                cells[(row, col)] = cell

        return cells

    def _load_board2_strip(self):
        """Read CTS_mapping_board2.txt and return [[row0_channels], [row1_channels]].
        Searches: script dir, cwd, then the Janus-UMD default location."""
        candidates = [
            os.path.join(_SCRIPT_DIR, 'CTS_mapping_board2.txt'),
            os.path.join(os.getcwd(), 'CTS_mapping_board2.txt'),
            'C:/UMD-END/Janus-UMD/gui/CTS_mapping_board2.txt',
        ]
        for path in candidates:
            try:
                with open(path, 'r') as f:
                    lines = [l.strip() for l in f if l.strip()]
                rows = [[int(x.strip()) for x in line.split(',')] for line in lines]
                print(f"Loaded Board 2 strip mapping from {path} "
                      f"({sum(len(r) for r in rows)} channels)")
                return rows
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"Error reading {path}: {e}")
        print("Board 2 strip mapping not found — strip will be empty")
        return None

    def _create_strip_row(self, parent, channels):
        """Create a horizontal row of labelled cells for the given channel list.
        Returns dict of ch -> Label widget."""
        cells = {}
        for col, ch in enumerate(channels):
            cell = tk.Label(parent, text=f"#{ch:02d}", bg=self.color_no_hit,
                           fg='white', font=('Courier', 9, 'bold'),
                           width=10, height=5,
                           relief=tk.RAISED, bd=1,
                           justify=tk.CENTER)
            cell.grid(row=0, column=col, padx=1, pady=0)
            cells[ch] = cell
        return cells

    def load_mapping_file(self, filename, board):
        """Load channel mapping from file"""
        def parse_mapping_file(path):
            with open(path, 'r') as f:
                lines = f.readlines()
            if len(lines) != 4:
                raise ValueError(f"Mapping file must have exactly 4 lines, found {len(lines)}")
            mapping = {}
            for row_idx, line in enumerate(lines):
                channels = [int(x.strip()) for x in line.strip().split(',')]
                if len(channels) != 16:
                    raise ValueError(f"Row {row_idx} must have 16 channels, found {len(channels)}")
                for col_idx, ch_num in enumerate(channels):
                    mapping[ch_num] = (row_idx, col_idx)
            return mapping

        loaded_path = None
        mapping = None

        try:
            mapping = parse_mapping_file(filename)
            loaded_path = filename
        except FileNotFoundError:
            basename = os.path.basename(filename)
            try:
                alt = os.path.join(os.getcwd(), basename)
                mapping = parse_mapping_file(alt)
                loaded_path = alt
            except FileNotFoundError:
                try:
                    alt2 = os.path.join(os.path.dirname(__file__), basename)
                    mapping = parse_mapping_file(alt2)
                    loaded_path = alt2
                except FileNotFoundError:
                    try:
                        alt3 = os.path.join(os.path.expanduser('~'), 'Janus-UMD', 'gui', basename)
                        mapping = parse_mapping_file(alt3)
                        loaded_path = alt3
                    except Exception:
                        print(f"Mapping file not found in tried locations for '{filename}' - will use default linear mapping")
                        mapping = None
                except Exception as e:
                    print(f"Error reading mapping file {alt2}: {e}")
                    mapping = None
            except Exception as e:
                print(f"Error reading mapping file {alt}: {e}")
                mapping = None
        except Exception as e:
            print(f"Error reading mapping file {filename}: {e}")
            mapping = None

        if mapping is None:
            mapping = {}
            for ch in range(64):
                row = ch // 16
                col = ch % 16
                mapping[ch] = (row, col)
        else:
            if board == 0:
                print(f"Loaded Board 0 mapping from {loaded_path}")
            else:
                print(f"Loaded Board 1 mapping from {loaded_path}")

        if board == 0:
            self.board0_mapping = mapping
        else:
            self.board1_mapping = mapping

    def load_data_file(self):
        """Load a data file (auto-detect mode). Reads raw bytes immediately,
        then parses only the first chunk of events for fast startup."""
        filename = filedialog.askopenfilename(
            title="Select Data File",
            filetypes=[("Binary Data", "*.dat"), ("All Files", "*.*")]
        )

        if not filename:
            return

        try:
            # Stop watch mode if active
            if self.watch_active:
                self.toggle_watch_mode()

            # Read the entire file into memory in one I/O call (fast),
            # but do NOT parse events yet.
            print(f"\n{'='*60}")
            print(f"Loading: {filename}")
            with open(filename, 'rb') as f:
                self.file_data = f.read()

            file_size_mb = len(self.file_data) / (1024 * 1024)
            file_size_kb = len(self.file_data) / 1024
            print(f"File size: {file_size_mb:.2f} MB ({len(self.file_data):,} bytes)")

            self.data_filename = filename

            # Always use SpecT mode
            self.unpacker = SpecTDataUnpacker(filename)
            self.unpacker._parse_header(self.file_data)
            self.data_mode = "SPECT_TIMING"
            self.mode_label.config(text="Mode: SPECT+TIMING", fg='#2ECC71')
            print(f"Mode: SPECT+TIMING")

            # Reset chunked-loading state
            self.raw_events = []
            self.unpacker.events = []
            self.parse_offset = self.unpacker.file_header_size
            self.events_parse_count = 0
            self.all_events_loaded = False

            # Always parse in chunk mode
            print(f"Parsing first chunk of {self.chunk_size} events...")
            self._parse_chunk()

            # Create realtime unpacker for watch mode
            self.realtime_unpacker = RealtimeEventUnpacker(filename, self.data_mode)

            if not self.raw_events:
                messagebox.showwarning("Warning", "No events found in file")
                return

            # Pair and display
            self.paired_events = self.pair_events_by_timestamp()
            self.filtered_events = self.paired_events
            self.current_event_idx = 0
            self.file_label.config(text=os.path.basename(filename))
            self._update_load_status()
            self.update_display()

            more_msg = "" if self.all_events_loaded else "\n(More events will load as you navigate)"
            messagebox.showinfo("Success",
                              f"File loaded: {file_size_kb:.1f} KB\n"
                              f"Initial events: {len(self.paired_events)} paired\n"
                              f"Mode: {self.data_mode}{more_msg}")

        except Exception as e:
            messagebox.showerror("Error", f"Error loading file: {e}")
            import traceback
            traceback.print_exc()

    def _parse_chunk(self):
        """
        Parse up to self.chunk_size events from self.file_data starting at
        self.parse_offset. Updates self.raw_events, self.parse_offset, and
        self.events_parse_count in-place.
        Returns the number of new events parsed.
        """
        if self.all_events_loaded or self.file_data is None:
            return 0

        parsed = 0
        data = self.file_data

        while parsed < self.chunk_size:
            if self.parse_offset + 13 > len(data):
                self.all_events_loaded = True
                break

            try:
                event, next_offset = self.unpacker._parse_event(
                    data, self.parse_offset, self.events_parse_count
                )
            except Exception as e:
                print(f"Parse error at offset {self.parse_offset}: {e}")
                self.all_events_loaded = True
                break

            if event is None or next_offset <= self.parse_offset:
                self.all_events_loaded = True
                break

            self.raw_events.append(event)
            self.unpacker.events.append(event)
            self.events_parse_count += 1
            self.parse_offset = next_offset
            parsed += 1

        # Also mark done if we've consumed all bytes
        if self.parse_offset + 13 >= len(data):
            self.all_events_loaded = True

        pct = 100.0 * self.parse_offset / len(data) if data else 0
        print(f"  Parsed {parsed} events | total: {self.events_parse_count} | "
              f"offset: {self.parse_offset:,}/{len(data):,} bytes ({pct:.1f}%)"
              + (" [DONE]" if self.all_events_loaded else ""))

        return parsed

    def _maybe_load_more(self):
        """
        Check whether we are within load_threshold events of the end of the
        currently filtered list. If so, parse the next chunk, re-pair all
        raw events, and re-apply the current filter.
        Called after every forward-navigation step.
        """
        if self.all_events_loaded or self.file_data is None:
            return

        remaining = len(self.filtered_events) - 1 - self.current_event_idx
        if remaining > self.load_threshold:
            return

        print(f"  [lazy load] {remaining} events remaining, fetching next chunk...")
        n = self._parse_chunk()
        if n == 0:
            return

        # Re-pair all raw events (incremental re-pairing is simpler/correct)
        self.paired_events = self.pair_events_by_timestamp()

        # Re-apply current filter to the extended paired list
        min_b0 = self.min_hits_board0.get()
        min_b1 = self.min_hits_board1.get()
        min_b2 = self.min_hits_board2.get()
        threshold = self.hg_threshold.get()
        new_filtered = self._filter_paired_events(
            self.paired_events, min_b0, min_b1, threshold, min_b2
        )
        # Preserve index; fall back to all-events if filter now returns nothing
        self.filtered_events = new_filtered if new_filtered else self.paired_events

        self._update_load_status()

    def _update_load_status(self):
        """Refresh the filter_status label."""
        min_b0 = self.min_hits_board0.get()
        min_b1 = self.min_hits_board1.get()
        min_b2 = self.min_hits_board2.get()

        if min_b0 == 0 and min_b1 == 0 and min_b2 == 0:
            if self.all_events_loaded:
                self.filter_status.config(text="Showing all events")
            else:
                self.filter_status.config(text="Loading…")
        else:
            showing = len(self.filtered_events)
            total = len(self.paired_events)
            self.filter_status.config(
                text=f"Filtered: {showing}/{total} events "
                     f"(B0>={min_b0}, B1>={min_b1}, B2>={min_b2})"
            )

    def apply_filter(self):
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
                                 f"No events match criteria:\n"
                                 f"Board 0 >= {min_b0} hits\n"
                                 f"Board 1 >= {min_b1} hits\n"
                                 f"Board 2 >= {min_b2} hits")
            self.filtered_events = self.paired_events  # Reset to all
            self.filter_status.config(text="Showing all events (no matches)")
            return

        self.current_event_idx = 0
        self.update_display()
        self._update_load_status()

    def pair_events_by_timestamp(self):
        """Group events from all boards by timestamp (within 1 µs).

        Supports board_id 0, 1, and 2.  When chunked loading is active, the
        last 10 raw events are held back so events at a chunk boundary are
        not prematurely committed as incomplete pairs.
        """
        LOOKAHEAD = 10
        WINDOW    = 15   # max look-ahead when searching for board partners

        if not self.all_events_loaded and len(self.raw_events) > LOOKAHEAD:
            events_to_pair = self.raw_events[:-LOOKAHEAD]
        else:
            events_to_pair = self.raw_events

        paired = []
        used   = set()

        for i, evt in enumerate(events_to_pair):
            if i in used:
                continue

            bid = evt.board_id          # 0, 1, or 2
            pair = {'board0': None, 'board1': None, 'board2': None,
                    'timestamp': evt.timestamp_us}
            pair[f'board{bid}'] = evt
            used.add(i)

            # Collect the other two boards within the look-ahead window
            needed = {0, 1, 2} - {bid}
            for j in range(i + 1, min(i + WINDOW, len(events_to_pair))):
                if j in used or not needed:
                    continue
                other = events_to_pair[j]
                ob = other.board_id
                if ob in needed and abs(other.timestamp_us - evt.timestamp_us) < 1.0:
                    pair[f'board{ob}'] = other
                    used.add(j)
                    needed.discard(ob)

            paired.append(pair)

        return paired

    def update_display(self):
        """Update the display with current event data"""
        if not self.filtered_events:
            return

        # Clear all cells first
        for cells in [self.board0_cells, self.board1_cells]:
            for cell in cells.values():
                cell.config(text="", bg=self.color_no_hit)
        for ch, cell in {**self.board2_strip_cells_top, **self.board2_strip_cells_bot}.items():
            cell.config(text=f"#{ch:02d}", bg=self.color_no_hit)

        current_pair = self.filtered_events[self.current_event_idx]

        if current_pair['board0']:
            self.display_board_event(current_pair['board0'], self.board0_cells,
                                    self.board0_mapping)

        if current_pair['board1']:
            self.display_board_event(current_pair['board1'], self.board1_cells,
                                    self.board1_mapping)

        if current_pair.get('board2'):
            self.display_strip_event(current_pair['board2'])

        board0_hits = current_pair['board0'].num_hits if current_pair['board0'] else 0
        board1_hits = current_pair['board1'].num_hits if current_pair['board1'] else 0
        board2_hits = current_pair['board2'].num_hits if current_pair.get('board2') else 0

        self.event_info.config(
            text=f"Event #{self.current_event_idx + 1}/{len(self.filtered_events)}  |  "
                 f"Timestamp: {current_pair['timestamp']:.4f} µs  |  "
                 f"B0: {board0_hits} hits  |  B1: {board1_hits} hits  |  B2: {board2_hits} hits"
        )

    def display_board_event(self, event, cells, mapping):
        """
        Display event data in the board cells
        New format:
            Row 1: #CH
            Row 2: HG/LG (or -- if not present)
            Row 3: ToA/ToT (or -- if not present)

        Color coding:
            - TIMING mode: Red if hit present
            - SPECT_TIMING mode: Red only if HG > threshold, otherwise Blue
        """
        hit_data = {}
        for hit in event.hits:
            hit_data[hit.channel] = hit

        for ch in range(64):
            if ch not in mapping:
                continue

            row, col = mapping[ch]
            cell = cells[(row, col)]

            if ch in hit_data:
                hit = hit_data[ch]

                line1 = f"#{ch:02d}"

                if self.data_mode == "SPECT_TIMING":
                    hg_str = f"{hit.energy_hg:04d}" if hit.energy_hg is not None else " ---"
                    lg_str = f"{hit.energy_lg:04d}" if hit.energy_lg is not None else " ---"
                    line2 = f"{hg_str}/{lg_str}"
                else:
                    line2 = " ---/ ---"

                toa_str = f"{hit.toa:04d}" if hit.toa is not None else " ---"
                tot_str = f"{hit.tot:03d}" if hit.tot is not None else "---"
                line3 = f"{toa_str}/{tot_str}"

                text = f"{line1}\n{line2}\n{line3}"

                if self.data_mode == "SPECT_TIMING":
                    if hit.energy_hg is not None and hit.energy_hg > self.hg_threshold.get():
                        cell_color = self.color_hit
                    else:
                        cell_color = self.color_no_hit
                else:
                    cell_color = self.color_hit

                cell.config(text=text, bg=cell_color)
            else:
                cell.config(text=f"#{ch:02d}", bg=self.color_no_hit)

    def display_strip_event(self, event):
        """Display board2 event hits in the strip cells (keyed by channel number)."""
        hit_data = {hit.channel: hit for hit in event.hits}
        threshold = self.hg_threshold.get()
        all_strip = {**self.board2_strip_cells_top, **self.board2_strip_cells_bot}

        for ch, cell in all_strip.items():
            if ch in hit_data:
                hit = hit_data[ch]
                line1 = f"#{ch:02d}"
                if self.data_mode == "SPECT_TIMING":
                    hg_str = f"{hit.energy_hg:04d}" if hit.energy_hg is not None else " ---"
                    lg_str = f"{hit.energy_lg:04d}" if hit.energy_lg is not None else " ---"
                    line2 = f"{hg_str}/{lg_str}"
                else:
                    line2 = " ---/ ---"
                toa_str = f"{hit.toa:04d}" if hit.toa is not None else " ---"
                tot_str = f"{hit.tot:03d}" if hit.tot is not None else "---"
                text = f"{line1}\n{line2}\n{toa_str}/{tot_str}"
                if self.data_mode == "SPECT_TIMING":
                    color = (self.color_hit
                             if hit.energy_hg is not None and hit.energy_hg > threshold
                             else self.color_no_hit)
                else:
                    color = self.color_hit
                cell.config(text=text, bg=color)
            # cells not in hit_data were already reset to blue by update_display

    def first_event(self):
        """Go to first event"""
        if self.filtered_events:
            self.current_event_idx = 0
            self.update_display()

    def last_event(self):
        """Go to last event"""
        if self.filtered_events:
            self.current_event_idx = len(self.filtered_events) - 1
            self.update_display()

    def next_event(self):
        """Go to next event; trigger lazy chunk load if near end of loaded events"""
        if self.filtered_events and self.current_event_idx < len(self.filtered_events) - 1:
            self.current_event_idx += 1
            self.update_display()
            self._maybe_load_more()

    def prev_event(self):
        """Go to previous event"""
        if self.filtered_events and self.current_event_idx > 0:
            self.current_event_idx -= 1
            self.update_display()

    def toggle_watch_mode(self):
        """Start/stop watching file for new events"""
        if not self.realtime_unpacker:
            messagebox.showwarning("Warning", "No file loaded")
            return

        self.watch_active = not self.watch_active

        if self.watch_active:
            self.watch_button.config(text="⏸ Stop Watching", bg='#E74C3C')
            self.watch_status.config(text="Watch: ACTIVE", fg='#2ECC71')
            self.check_for_new_events()
        else:
            self.watch_button.config(text="▶ Watch File", bg='#9B59B6')
            self.watch_status.config(text="Watch: OFF", fg='#95A5A6')
            if self.watch_after_id:
                self.root.after_cancel(self.watch_after_id)
                self.watch_after_id = None

    def check_for_new_events(self):
        """Poll for new events and update display if matches current filters"""
        if not self.watch_active or not self.realtime_unpacker:
            return

        try:
            new_events = self.realtime_unpacker.read_new_events()

            if new_events:
                self.raw_events.extend(new_events)
                self.paired_events = self.pair_events_by_timestamp()

                min_b0 = self.min_hits_board0.get()
                min_b1 = self.min_hits_board1.get()
                min_b2 = self.min_hits_board2.get()
                threshold = self.hg_threshold.get()

                self.filtered_events = self._filter_paired_events(
                    self.paired_events, min_b0, min_b1, threshold, min_b2
                )

                if self.filtered_events:
                    self.current_event_idx = len(self.filtered_events) - 1
                    self.update_display()
                    self._update_load_status()

        except Exception as e:
            print(f"Error reading new events: {e}")

        if self.watch_active:
            self.watch_after_id = self.root.after(500, self.check_for_new_events)

    def _filter_paired_events(self, paired_events, min_b0, min_b1, threshold, min_b2=0):
        """Helper to filter paired events by hit counts and threshold"""
        filtered = []

        for pair in paired_events:
            if pair['board0']:
                if self.data_mode == "SPECT_TIMING":
                    board0_hits = sum(1 for hit in pair['board0'].hits
                                     if hit.energy_hg is not None and hit.energy_hg > threshold)
                else:
                    board0_hits = pair['board0'].num_hits
            else:
                board0_hits = 0

            if pair['board1']:
                if self.data_mode == "SPECT_TIMING":
                    board1_hits = sum(1 for hit in pair['board1'].hits
                                     if hit.energy_hg is not None and hit.energy_hg > threshold)
                else:
                    board1_hits = pair['board1'].num_hits
            else:
                board1_hits = 0

            if pair.get('board2'):
                if self.data_mode == "SPECT_TIMING":
                    board2_hits = sum(1 for hit in pair['board2'].hits
                                     if hit.energy_hg is not None and hit.energy_hg > threshold)
                else:
                    board2_hits = pair['board2'].num_hits
            else:
                board2_hits = 0

            if board0_hits >= min_b0 and board1_hits >= min_b1 and board2_hits >= min_b2:
                filtered.append(pair)

        return filtered


    def save_interesting_event(self):
        """Append the current event's number and timestamp to a CSV file."""
        if not self.filtered_events:
            messagebox.showwarning("Warning", "No events loaded")
            return

        # Ask for file path on first save
        if self.interesting_events_file is None:
            path = filedialog.asksaveasfilename(
                title="Save Interesting Events CSV",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            if not path:
                return
            self.interesting_events_file = path
            # Write header if file doesn't exist yet
            if not os.path.exists(path):
                with open(path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["display_index", "timestamp_us",
                                     "board0_event_num", "board1_event_num", "trigger_id"])

        pair = self.filtered_events[self.current_event_idx]
        display_index = self.current_event_idx + 1
        timestamp_us = pair['timestamp']
        b0_num = pair['board0'].event_number if pair['board0'] else ""
        b1_num = pair['board1'].event_number if pair['board1'] else ""
        trig = (pair['board0'].trigger_id if pair['board0']
                else pair['board1'].trigger_id if pair['board1'] else "")

        with open(self.interesting_events_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([display_index, f"{timestamp_us:.6f}", b0_num, b1_num, trig])

        print(f"  [save] Event #{display_index} @ {timestamp_us:.4f} µs saved to "
              f"{os.path.basename(self.interesting_events_file)}")

    def toggle_histogram_task(self):
        """Start or stop the background histogram-building thread."""
        if self.hist_running:
            # Signal the thread to stop
            with self.hist_lock:
                self.hist_running = False
            self.hist_button.config(text="▶ Build Histograms", bg='#1ABC9C')
            if self.hist_update_id:
                self.root.after_cancel(self.hist_update_id)
                self.hist_update_id = None
            return

        if self.file_data is None or self.unpacker is None:
            messagebox.showwarning("Warning", "No file loaded")
            return

        if self.hist_thread and self.hist_thread.is_alive():
            return  # Already running

        # Snapshot the current filter settings
        self.hist_filter_min_b0 = self.min_hits_board0.get()
        self.hist_filter_min_b1 = self.min_hits_board1.get()
        self.hist_filter_min_b2 = self.min_hits_board2.get()
        self.hist_filter_threshold = self.hg_threshold.get()

        with self.hist_lock:
            self.hist_running = True
            self.hist_events_read = 0

        self.hist_data = None
        self.hist_button.config(text="⏸ Stop Histograms", bg='#E74C3C')
        self.hist_count_label.config(text="Events processed: 0", fg='#2ECC71')

        self.hist_thread = threading.Thread(target=self._histogram_worker, daemon=True)
        self.hist_thread.start()

        # Schedule first count update after 10 seconds
        self.hist_update_id = self.root.after(10000, self._update_histogram_count)

    def _histogram_worker(self):
        """Background thread: parse entire file and accumulate per-channel histograms.

        Builds two sets:
          'all'      — every event in the file
          'filtered' — only events whose pair passes the filter that was active
                       when the histogram task was launched

        Data is organised as: hist[board_id][channel] = [values]
        Missing values are stored as -1.
        """
        data = self.file_data
        offset = self.unpacker.file_header_size
        min_b0    = self.hist_filter_min_b0
        min_b1    = self.hist_filter_min_b1
        min_b2    = self.hist_filter_min_b2
        threshold = self.hist_filter_threshold

        NBINS = 4096

        def make_boards():
            return {0: {}, 1: {}, 2: {}}

        def get_hist(d, board, ch):
            """Return the 4096-bin histogram array for (board, ch), creating if needed."""
            return d[board].setdefault(ch, np.zeros(NBINS, dtype=np.int32))

        def fill(d, board, ch, value):
            if value is not None and 0 <= value < NBINS:
                get_hist(d, board, ch)[value] += 1

        hg    = make_boards()
        lg    = make_boards()
        toa_h = make_boards()
        tot_h = make_boards()

        all_parsed = []   # keep every event for post-parse pairing/filtering
        count = 0

        # ── Pass 1: parse all events, accumulate all-events histograms ──────
        while offset < len(data) - 27:
            with self.hist_lock:
                if not self.hist_running:
                    break

            try:
                event, next_offset = self.unpacker._parse_event(data, offset, count)
            except Exception:
                break

            if event is None or next_offset <= offset:
                break

            b = event.board_id   # 0, 1, or 2
            for hit in event.hits:
                ch = hit.channel
                fill(hg,    b, ch, hit.energy_hg)
                fill(lg,    b, ch, hit.energy_lg)
                fill(toa_h, b, ch, hit.toa)
                fill(tot_h, b, ch, hit.tot)

            all_parsed.append(event)
            count += 1
            offset = next_offset

            with self.hist_lock:
                self.hist_events_read = count

        with self.hist_lock:
            self.hist_events_read = count
            self.hist_running = False

        # ── Pass 2: pair events and apply the filter ─────────────────────────
        pairs = self._pair_raw_events(all_parsed)
        filtered_pairs = self._filter_paired_events(pairs, min_b0, min_b1, threshold, min_b2)

        filtered_ids = set()
        for pair in filtered_pairs:
            for key in ('board0', 'board1', 'board2'):
                if pair.get(key):
                    filtered_ids.add(id(pair[key]))

        hg_f   = make_boards()
        lg_f   = make_boards()
        toa_hf = make_boards()
        tot_hf = make_boards()

        for event in all_parsed:
            if id(event) not in filtered_ids:
                continue
            b = event.board_id   # 0, 1, or 2
            for hit in event.hits:
                ch = hit.channel
                fill(hg_f,   b, ch, hit.energy_hg)
                fill(lg_f,   b, ch, hit.energy_lg)
                fill(toa_hf, b, ch, hit.toa)
                fill(tot_hf, b, ch, hit.tot)

        self.hist_data = {
            'all':      {'hg': hg,   'lg': lg,   'toa': toa_h,  'tot': tot_h},
            'filtered': {'hg': hg_f, 'lg': lg_f, 'toa': toa_hf, 'tot': tot_hf},
            'filter_params': {
                'min_hits_board0': min_b0,
                'min_hits_board1': min_b1,
                'min_hits_board2': min_b2,
                'hg_threshold':    threshold,
            },
        }

        total_ch = sum(len(hg[b]) for b in hg)
        filt_evts = len(filtered_ids)
        print(f"  [histogram] Done. {count} total events, "
              f"{filt_evts} passed filter, "
              f"{total_ch} board/channel combinations with data.")

        self._save_histograms_hdf5()

    def _pair_raw_events(self, events):
        """Pair a list of raw events by timestamp — same algorithm as the GUI.
        Supports board_id 0, 1, and 2.  Used by the histogram worker."""
        WINDOW = 15
        paired = []
        used   = set()

        for i, evt in enumerate(events):
            if i in used:
                continue

            bid  = evt.board_id
            pair = {'board0': None, 'board1': None, 'board2': None,
                    'timestamp': evt.timestamp_us}
            pair[f'board{bid}'] = evt
            used.add(i)

            needed = {0, 1, 2} - {bid}
            for j in range(i + 1, min(i + WINDOW, len(events))):
                if j in used or not needed:
                    continue
                other = events[j]
                ob = other.board_id
                if ob in needed and abs(other.timestamp_us - evt.timestamp_us) < 1.0:
                    pair[f'board{ob}'] = other
                    used.add(j)
                    needed.discard(ob)

            paired.append(pair)

        return paired

    def _save_histograms_hdf5(self):
        """Write self.hist_data to an HDF5 file beside the source data file.

        Structure:
          /all/board_N/channel_M/{hg, lg, toa, tot}   — every event
          /filtered/board_N/channel_M/{hg, lg, toa, tot} — filter-passing events
              /filtered.attrs: min_hits_board0, min_hits_board1, hg_threshold
        Each dataset is a 1-D int32 array of raw sample values (-1 = not present).
        """
        if self.hist_data is None or self.data_filename is None:
            return

        stem = os.path.splitext(os.path.basename(self.data_filename))[0]
        h5_path = os.path.join(os.getcwd(), stem + "_hist.h5")

        def write_board_channel_group(parent_grp, data_dict):
            """Write board_N/channel_M/{hg,lg,toa,tot} under parent_grp.
            Each dataset is a 4096-bin int32 histogram array."""
            for board_id in (0, 1, 2):
                bgrp = parent_grp.create_group(f"board_{board_id}")
                channels = sorted(set(
                    list(data_dict['hg'][board_id]) +
                    list(data_dict['lg'][board_id]) +
                    list(data_dict['toa'][board_id]) +
                    list(data_dict['tot'][board_id])
                ))
                for ch in channels:
                    cgrp = bgrp.create_group(f"channel_{ch}")
                    for key in ('hg', 'lg', 'toa', 'tot'):
                        hist = data_dict[key][board_id].get(ch)
                        if hist is not None:
                            cgrp.create_dataset(key, data=hist, compression='gzip')

        try:
            with h5py.File(h5_path, 'w') as f:
                f.attrs['source_file'] = self.data_filename
                f.attrs['total_events'] = self.hist_events_read

                write_board_channel_group(f.create_group('all'),
                                          self.hist_data['all'])

                fgrp = f.create_group('filtered')
                fp = self.hist_data['filter_params']
                fgrp.attrs['min_hits_board0'] = fp['min_hits_board0']
                fgrp.attrs['min_hits_board1'] = fp['min_hits_board1']
                fgrp.attrs['min_hits_board2'] = fp['min_hits_board2']
                fgrp.attrs['hg_threshold']    = fp['hg_threshold']
                write_board_channel_group(fgrp, self.hist_data['filtered'])

            print(f"  [histogram] Saved to {h5_path}")
        except Exception as e:
            print(f"  [histogram] Error saving HDF5: {e}")

    def _update_histogram_count(self):
        """Timer callback: update the event-count label every 10 seconds."""
        with self.hist_lock:
            count = self.hist_events_read
            still_running = self.hist_running

        if still_running:
            self.hist_count_label.config(
                text=f"Events processed: {count:,}", fg='#2ECC71')
            self.hist_update_id = self.root.after(10000, self._update_histogram_count)
        else:
            self.hist_count_label.config(
                text=f"Events processed: {count:,} [Done]", fg='#F39C12')
            self.hist_button.config(text="▶ Build Histograms", bg='#1ABC9C')
            self.hist_update_id = None


def main():
    root = tk.Tk()
    app = UnifiedEventViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
