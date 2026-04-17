#!/usr/bin/env python3
"""
Realtime Event Unpacker for JanusC
Reads new events from .dat file without re-parsing old data (Option A approach)

Wraps existing TimingDataUnpacker and SpecTDataUnpacker for incremental reading.

Author: Claude (with Paul)
Date: January 2026
"""

import struct
from .timing_unpacker import TimingDataUnpacker
from .spect_t_unpacker import SpecTDataUnpacker


class RealtimeEventUnpacker:
    """
    Wrapper that reads only new events from an active file.
    Safely avoids incomplete events at EOF.
    """

    def __init__(self, filename, mode):
        """
        Args:
            filename: path to .dat file
            mode: "TIMING" or "SPECT_TIMING"
        """
        self.filename = filename
        self.mode = mode
        self.file_header_size = 25  # Default, set dynamically later

        # Create underlying unpacker based on mode
        if mode == "TIMING":
            self.unpacker = TimingDataUnpacker(filename)
        else:
            self.unpacker = SpecTDataUnpacker(filename)

        # Track where we last successfully read
        self.last_safe_offset = self.file_header_size

    def read_new_events(self):
        """
        Read only new events since last call.
        Returns list of new UnifiedEvent objects.
        """
        try:
            with open(self.filename, 'rb') as f:
                f.seek(0)
                data = f.read()
        except (IOError, OSError):
            # File might be locked or being written
            return []

        if len(data) >= 1:
            num_boards = data[0]
            self.file_header_size = 9 + 8 * num_boards
            
        if self.last_safe_offset < self.file_header_size:
            self.last_safe_offset = self.file_header_size

        if len(data) <= self.last_safe_offset:
            # No new data
            return []

        new_events = []
        offset = self.last_safe_offset

        # Try to parse events from last_safe_offset onward
        while offset < len(data) - 13:  # Need at least 13 bytes for minimal header

            # Try to read event size
            if offset + 2 > len(data):
                # Incomplete size field - stop here
                break

            event_size = struct.unpack('<H', data[offset:offset+2])[0]

            # Check if we have the complete event
            if offset + event_size > len(data):
                # Incomplete event - don't parse, stop here
                break

            # Event is complete, parse it
            try:
                event, next_offset = self.unpacker._parse_event(
                    data, offset, len(self.unpacker.events)
                )

                if event is None:
                    break

                new_events.append(event)
                self.unpacker.events.append(event)
                self.last_safe_offset = next_offset
                offset = next_offset

            except Exception as e:
                # Parsing error - stop and save offset
                print(f"Warning: parsing error at offset {offset}: {e}")
                break

        return new_events

    def reset(self):
        """Reset the unpacker (e.g., when file is reloaded)"""
        self.unpacker.events = []
        self.last_safe_offset = self.file_header_size


def detect_file_mode(filename):
    """
    Detect whether file is TIMING or SPECT_TIMING by reading header.
    Returns "TIMING" or "SPECT_TIMING"
    """
    try:
        with open(filename, 'rb') as f:
            header = f.read(64) # Read enough for dynamic header

        if len(header) < 1:
            return None
            
        num_boards = header[0]
        file_header_size = 9 + 8 * num_boards

        if len(header) < file_header_size:
            return None

        # Mode byte is expected to be the last byte of the file header
        mode_byte = header[file_header_size - 1]

        if mode_byte == 1:
            return "SPECT_TIMING"
        else:
            return "TIMING"

    except Exception as e:
        print(f"Error detecting mode: {e}")
        return None
