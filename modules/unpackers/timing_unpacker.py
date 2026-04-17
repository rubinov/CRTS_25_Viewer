#!/usr/bin/env python3
"""
TIMING Mode Binary Data Unpacker for JanusC
Extracts event data from .dat files written in TIMING, COMMON START mode
Updated to use unified data structures

Author: Claude (with Paul)
Date: January 2026
"""

import struct
from typing import List
from .unified_data_structures import UnifiedHit, UnifiedEvent


class TimingDataUnpacker:
    """
    Unpacks TIMING mode binary data files from JanusC

    Binary format per event:
        size: uint16_t (2 bytes) - total event size including this field
        board_id: uint8_t (1 byte) - which board (0 or 1)
        timestamp: double (8 bytes) - fine timestamp in microseconds
        nhits: uint16_t (2 bytes) - number of hits in this event

        For each hit:
            channel: uint8_t (1 byte) - channel number (0-63)
            datatype: uint8_t (1 byte) - bitmask (0x10=ToA, 0x20=ToT, 0x30=both)
            if (datatype & 0x10): toa: uint32_t (4 bytes) - Time of Arrival in LSB
            if (datatype & 0x20): tot: uint16_t (2 bytes) - Time over Threshold in LSB
    """

    def __init__(self, filename):
        self.filename = filename
        self.events = []
        self.file_header_size = 25  # First 25 bytes are file header

    def unpack(self):
        """Unpack all events from the binary file"""
        with open(self.filename, 'rb') as f:
            data = f.read()

        print(f"File size: {len(data)} bytes")
        print(f"Skipping {self.file_header_size} byte header...")

        # Skip file header
        offset = self.file_header_size
        event_num = 0

        while offset < len(data) - 13:  # Need at least 13 bytes for header
            event, next_offset = self._parse_event(data, offset, event_num)

            if event is None:
                break

            self.events.append(event)
            event_num += 1
            offset = next_offset

        print(f"Unpacked {len(self.events)} events\n")
        return self.events

    def _parse_event(self, data, offset, event_num):
        """Parse a single timing event"""

        # Check if we have enough data for event header
        if offset + 13 > len(data):
            return None, offset

        # Parse event header
        size = struct.unpack('<H', data[offset:offset+2])[0]
        board_id = data[offset+2]
        timestamp_us = struct.unpack('<d', data[offset+3:offset+11])[0]
        nhits = struct.unpack('<H', data[offset+11:offset+13])[0]

        # Parse hits
        hits = []
        hit_offset = offset + 13

        for _ in range(nhits):
            if hit_offset + 2 > len(data):
                break

            channel = data[hit_offset]
            datatype = data[hit_offset + 1]
            hit_offset += 2

            # Parse ToA if present (bit 4 set)
            toa = None
            if datatype & 0x10:
                if hit_offset + 4 > len(data):
                    break
                toa = struct.unpack('<I', data[hit_offset:hit_offset+4])[0]
                hit_offset += 4

            # Parse ToT if present (bit 5 set)
            tot = None
            if datatype & 0x20:
                if hit_offset + 2 > len(data):
                    break
                tot = struct.unpack('<H', data[hit_offset:hit_offset+2])[0]
                hit_offset += 2

            hits.append(UnifiedHit(
                channel=channel,
                datatype=datatype,
                energy_lg=None,  # No energy in timing mode
                energy_hg=None,
                toa=toa,
                tot=tot
            ))

        event = UnifiedEvent(
            event_number=event_num,
            board_id=board_id,
            timestamp_us=timestamp_us,
            trigger_id=0,  # Not in timing mode event structure
            num_hits=nhits,
            hits=hits,
            channel_mask=0,  # Not used in timing mode
            mode="TIMING"
        )

        # Next event starts at current offset + size
        next_offset = offset + size

        return event, next_offset

    def get_events_by_board(self, board_id):
        """Get all events from a specific board"""
        return [ev for ev in self.events if ev.board_id == board_id]

    def get_channel_hits(self, board_id, channel):
        """
        Get all hits for a specific board and channel
        Returns list of (event_number, timestamp_us, hit) tuples
        """
        hits = []
        for event in self.events:
            if event.board_id == board_id:
                for hit in event.hits:
                    if hit.channel == channel:
                        hits.append((event.event_number, event.timestamp_us, hit))
        return hits

    def summary(self):
        """Print summary statistics"""
        if not self.events:
            print("No events loaded")
            return

        total_events = len(self.events)
        board_ids = set(ev.board_id for ev in self.events)
        total_hits = sum(ev.num_hits for ev in self.events)

        print(f"{'='*70}")
        print(f"TIMING Mode Data Summary")
        print(f"{'='*70}")
        print(f"File: {self.filename}")
        print(f"Total Events: {total_events}")
        print(f"Boards Present: {sorted(board_ids)}")
        print(f"Total Hits: {total_hits}")
        print(f"Average Hits/Event: {total_hits/total_events:.2f}")

        for board in sorted(board_ids):
            board_events = self.get_events_by_board(board)
            board_hits = sum(ev.num_hits for ev in board_events)
            print(f"\nBoard {board}:")
            print(f"  Events: {len(board_events)}")
            print(f"  Hits: {board_hits}")
            print(f"  Time range: {board_events[0].timestamp_us:.3f} - "
                  f"{board_events[-1].timestamp_us:.3f} µs")
            print(f"  Duration: {board_events[-1].timestamp_us - board_events[0].timestamp_us:.3f} µs")

        print(f"{'='*70}\n")
