#!/usr/bin/env python3
"""
SPECTROSCOPY+TIMING Mode Binary Data Unpacker for JanusC
Extracts event data from .dat files written in SPECT+TIMING mode

Author: Claude (with Paul)
Date: January 2026
"""

import struct
from .unified_data_structures import UnifiedHit, UnifiedEvent

# Pre-compiled struct objects — format strings are parsed once at import time,
# not on every unpack call.
_U16 = struct.Struct('<H')   # uint16
_U32 = struct.Struct('<I')   # uint32
_U64 = struct.Struct('<Q')   # uint64
_F32 = struct.Struct('<f')   # float32
_F64 = struct.Struct('<d')   # float64 (timestamp)


class SpecTDataUnpacker:
    """
    Unpacks SPECTROSCOPY+TIMING mode binary data files from JanusC

    Binary format per event:
        size:         uint16_t (2 bytes)  - total event size including this field
        board_id:     uint8_t  (1 byte)   - which board (0 or 1)
        timestamp:    double   (8 bytes)  - event timestamp in microseconds
        trigger_id:   uint64_t (8 bytes)  - trigger ID
        channel_mask: uint64_t (8 bytes)  - bitmask of channels with data

        For each channel in mask:
            channel:  uint8_t (1 byte)  - channel number (0-63)
            datatype: uint8_t (1 byte)  - bitmask:
                0x01 = LG energy present
                0x02 = HG energy present
                0x10 = ToA present
                0x20 = ToT present

            if (datatype & 0x01): energy_lg: uint16_t (2 bytes)
            if (datatype & 0x02): energy_hg: uint16_t (2 bytes)
            if (datatype & 0x10):
                if OutFileUnit==1: toa: float32 (4 bytes) in ns
                else:              toa: uint16_t (2 bytes) in LSB
            if (datatype & 0x20):
                if OutFileUnit==1: tot: float32 (4 bytes) in ns
                else:              tot: uint16_t (2 bytes) in LSB
    """

    def __init__(self, filename):
        self.filename = filename
        self.events = []
        self.file_header_size = 25  # Will be dynamically updated in _parse_header
        self.time_unit = 0          # 0 = LSB, 1 = nanoseconds
        self.toa_lsb_ns = 0.5       # Default LSB value in ns

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def unpack(self):
        """Read and unpack all events from the binary file."""
        with open(self.filename, 'rb') as f:
            data = f.read()

        print(f"File size: {len(data):,} bytes")
        self._parse_header(data)
        print(f"Time unit: {'nanoseconds' if self.time_unit else 'LSB'}, "
              f"ToA LSB: {self.toa_lsb_ns} ns")

        offset = self.file_header_size
        event_num = 0

        while offset < len(data) - 13:
            event, next_offset = self._parse_event(data, offset, event_num)
            if event is None:
                break
            self.events.append(event)
            event_num += 1
            offset = next_offset

        print(f"Unpacked {len(self.events):,} events\n")
        return self.events

    def get_events_by_board(self, board_id):
        """Return all events from a specific board."""
        return [ev for ev in self.events if ev.board_id == board_id]

    def get_channel_hits(self, board_id, channel):
        """
        Return all hits for a specific board and channel as
        (event_number, timestamp_us, hit) tuples.
        """
        result = []
        for event in self.events:
            if event.board_id == board_id:
                for hit in event.hits:
                    if hit.channel == channel:
                        result.append((event.event_number, event.timestamp_us, hit))
        return result

    def summary(self):
        """Print summary statistics."""
        if not self.events:
            print("No events loaded")
            return

        total_events = len(self.events)
        board_ids = sorted(set(ev.board_id for ev in self.events))
        total_hits = sum(ev.num_hits for ev in self.events)

        sep = '=' * 70
        print(sep)
        print("SPECTROSCOPY+TIMING Mode Data Summary")
        print(sep)
        print(f"File:               {self.filename}")
        print(f"Total events:       {total_events:,}")
        print(f"Boards present:     {board_ids}")
        print(f"Total hits:         {total_hits:,}")
        print(f"Avg hits/event:     {total_hits / total_events:.2f}")

        for board in board_ids:
            bevts = self.get_events_by_board(board)
            bhits = sum(ev.num_hits for ev in bevts)
            t0 = bevts[0].timestamp_us
            t1 = bevts[-1].timestamp_us
            print(f"\nBoard {board}:")
            print(f"  Events:     {len(bevts):,}")
            print(f"  Hits:       {bhits:,}")
            print(f"  Time range: {t0:.3f} – {t1:.3f} µs")
            print(f"  Duration:   {t1 - t0:.3f} µs")

        print(sep + '\n')

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_header(self, data):
        """Parse the dynamic file header."""
        if len(data) >= 1:
            num_boards = data[0]
            if 0 < num_boards <= 16:
                self.file_header_size = 1 + 8 * num_boards
            else:
                self.file_header_size = 25  # Fallback
        else:
            print("Warning: file too small for header")
            return

        if len(data) < self.file_header_size:
            print(f"Warning: file too small for {self.file_header_size}-byte header")
            return
            
        self.time_unit  = data[12]
        self.toa_lsb_ns = _F32.unpack_from(data, 13)[0]

    def _parse_event(self, data, offset, event_num):
        """Parse a single event starting at *offset*.

        Returns (UnifiedEvent, next_offset) on success, or (None, offset) if
        the buffer does not contain a complete event at that position.
        Called by the chunked loader and the realtime watch-mode unpacker.
        """
        data_len = len(data)
        if offset + 27 > data_len:
            return None, offset

        size         = _U16.unpack_from(data, offset)[0]
        board_id     = data[offset + 2]
        timestamp_us = _F64.unpack_from(data, offset + 3)[0]
        trigger_id   = _U64.unpack_from(data, offset + 11)[0]
        channel_mask = _U64.unpack_from(data, offset + 19)[0]

        # Sanity check: size must cover the 27-byte header and not exceed buffer
        if size < 27 or offset + size > data_len:
            return None, offset

        time_unit  = self.time_unit
        toa_lsb_ns = self.toa_lsb_ns

        hits = []
        ho   = offset + 27
        end  = offset + size

        while ho + 2 <= end:
            channel  = data[ho]
            datatype = data[ho + 1]
            ho      += 2

            energy_lg = energy_hg = toa = tot = None

            if datatype & 0x01:
                energy_lg = _U16.unpack_from(data, ho)[0]; ho += 2
            if datatype & 0x02:
                energy_hg = _U16.unpack_from(data, ho)[0]; ho += 2
            if datatype & 0x10:
                if time_unit == 1:
                    toa = int(_F32.unpack_from(data, ho)[0]); ho += 4
                else:
                    toa = _U32.unpack_from(data, ho)[0]; ho += 4
            if datatype & 0x20:
                if time_unit == 1:
                    tot = int(_F32.unpack_from(data, ho)[0] / toa_lsb_ns); ho += 4
                else:
                    tot = _U16.unpack_from(data, ho)[0]; ho += 2

            if channel < 64:
                hits.append(UnifiedHit(
                    channel=channel,
                    datatype=datatype,
                    energy_lg=energy_lg,
                    energy_hg=energy_hg,
                    toa=toa,
                    tot=tot,
                ))

        event = UnifiedEvent(
            event_number=event_num,
            board_id=board_id,
            timestamp_us=timestamp_us,
            trigger_id=trigger_id,
            num_hits=len(hits),
            hits=hits,
            channel_mask=channel_mask,
            mode="SPECT_TIMING",
        )
        return event, offset + size
