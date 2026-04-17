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
        self.file_header_size = 25  # First 25 bytes are file header
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

        self.events = self._parse_all_events(data)
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
        """Parse the 25-byte file header."""
        if len(data) < 25:
            print("Warning: file too small for header")
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

        mask = channel_mask
        while mask and ho + 2 <= end:
            lsb      = mask & (-mask)
            mask    ^= lsb
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
                    toa = _U16.unpack_from(data, ho)[0]; ho += 2
            if datatype & 0x20:
                if time_unit == 1:
                    tot = int(_F32.unpack_from(data, ho)[0] / toa_lsb_ns); ho += 4
                else:
                    tot = _U16.unpack_from(data, ho)[0]; ho += 2

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

    def _parse_all_events(self, data):
        """
        Fast inner loop: parse every event in the buffer and return the list.

        Speed notes:
          - unpack_from avoids allocating a slice object on every field read.
          - Struct objects are pre-compiled at module level.
          - channel_mask is iterated by isolating set bits one at a time
            (mask & -mask trick) so we only visit channels that actually fired
            instead of always looping 64 times.
          - Hot-path values (time_unit, toa_lsb_ns, data_len) are cached as
            locals to avoid repeated attribute lookups inside the loop.
        """
        time_unit   = self.time_unit
        toa_lsb_ns  = self.toa_lsb_ns
        data_len    = len(data)
        offset      = self.file_header_size

        # Local aliases shave attribute-lookup overhead in the inner loop
        u16_unpack  = _U16.unpack_from
        u64_unpack  = _U64.unpack_from
        f32_unpack  = _F32.unpack_from
        f64_unpack  = _F64.unpack_from

        events     = []
        event_num  = 0

        while offset + 27 <= data_len:
            # ---- Event header (27 bytes) ----
            size         = u16_unpack(data, offset)[0]
            board_id     = data[offset + 2]
            timestamp_us = f64_unpack(data, offset + 3)[0]
            trigger_id   = u64_unpack(data, offset + 11)[0]
            channel_mask = u64_unpack(data, offset + 19)[0]

            hits = []
            ho   = offset + 27          # current position within hit data
            end  = offset + size        # hard stop: don't read past this event

            # ---- Iterate only over channels that fired ----
            mask = channel_mask
            while mask and ho + 2 <= end:
                lsb      = mask & (-mask)       # lowest set bit
                mask    ^= lsb                  # clear it
                channel  = data[ho]
                datatype = data[ho + 1]
                ho      += 2

                energy_lg = None
                energy_hg = None
                toa       = None
                tot       = None

                if datatype & 0x01:             # LG energy (uint16)
                    energy_lg = u16_unpack(data, ho)[0]
                    ho += 2

                if datatype & 0x02:             # HG energy (uint16)
                    energy_hg = u16_unpack(data, ho)[0]
                    ho += 2

                if datatype & 0x10:             # ToA
                    if time_unit == 1:          # float32 nanoseconds
                        toa = int(f32_unpack(data, ho)[0])
                        ho += 4
                    else:                       # uint16 LSB
                        toa = u16_unpack(data, ho)[0]
                        ho += 2

                if datatype & 0x20:             # ToT
                    if time_unit == 1:          # float32 nanoseconds
                        tot = int(f32_unpack(data, ho)[0] / toa_lsb_ns)
                        ho += 4
                    else:                       # uint16 LSB
                        tot = u16_unpack(data, ho)[0]
                        ho += 2

                hits.append(UnifiedHit(
                    channel=channel,
                    datatype=datatype,
                    energy_lg=energy_lg,
                    energy_hg=energy_hg,
                    toa=toa,
                    tot=tot,
                ))

            events.append(UnifiedEvent(
                event_number=event_num,
                board_id=board_id,
                timestamp_us=timestamp_us,
                trigger_id=trigger_id,
                num_hits=len(hits),
                hits=hits,
                channel_mask=channel_mask,
                mode="SPECT_TIMING",
            ))
            event_num += 1
            offset    += size           # jump to next event using size field

        return events
