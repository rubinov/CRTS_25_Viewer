#!/usr/bin/env python3
"""
Unified Data Structures for JanusC Binary Data
Supports both TIMING mode and SPECTROSCOPY+TIMING mode

Author: Claude (with Paul)
Date: January 2026
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class UnifiedHit:
    """
    Unified hit structure that works for both TIMING and SPECT+TIMING modes

    For TIMING mode: Only channel, datatype, toa, tot are populated
    For SPECT+TIMING mode: All fields may be populated
    """
    channel: int
    datatype: int  # Bitmask: 0x01=LG, 0x02=HG, 0x10=ToA, 0x20=ToT

    # Energy values (for SPECT+TIMING mode)
    energy_lg: Optional[int] = None  # Low gain energy
    energy_hg: Optional[int] = None  # High gain energy

    # Timing values (for TIMING and SPECT+TIMING modes)
    toa: Optional[int] = None  # Time of Arrival in LSB units
    tot: Optional[int] = None  # Time over Threshold in LSB units

    @property
    def toa_ns(self):
        """ToA in nanoseconds (LSB = 0.5 ns)"""
        return self.toa * 0.5 if self.toa is not None else None

    @property
    def tot_ns(self):
        """ToT in nanoseconds (LSB = 0.5 ns)"""
        return self.tot * 0.5 if self.tot is not None else None

    @property
    def has_energy(self):
        """Check if this hit has energy data"""
        return self.energy_lg is not None or self.energy_hg is not None

    @property
    def has_timing(self):
        """Check if this hit has timing data"""
        return self.toa is not None or self.tot is not None

    def __repr__(self):
        parts = [f"Ch{self.channel:2d}"]

        # Energy info
        if self.energy_lg is not None or self.energy_hg is not None:
            lg_str = f"{self.energy_lg:4d}" if self.energy_lg is not None else "  --"
            hg_str = f"{self.energy_hg:4d}" if self.energy_hg is not None else "  --"
            parts.append(f"LG={lg_str} HG={hg_str}")

        # Timing info
        if self.toa is not None or self.tot is not None:
            toa_str = f"{self.toa:4d}" if self.toa is not None else "  --"
            tot_str = f"{self.tot:4d}" if self.tot is not None else "  --"
            parts.append(f"ToA={toa_str} ToT={tot_str}")

        return " ".join(parts)


@dataclass
class UnifiedEvent:
    """
    Unified event structure for both TIMING and SPECT+TIMING modes
    """
    event_number: int      # Sequential event number in file
    board_id: int         # Board ID (0 or 1)
    timestamp_us: float   # Event timestamp in microseconds
    trigger_id: int       # Trigger ID
    num_hits: int         # Number of hits in this event
    hits: List[UnifiedHit]  # List of hits
    channel_mask: int = 0  # Channel mask (for SPECT+TIMING)
    mode: str = "UNKNOWN"  # "TIMING" or "SPECT_TIMING"

    def __repr__(self):
        return (f"Evt#{self.event_number:4d}: Brd={self.board_id} "
                f"T={self.timestamp_us:10.4f}us TrgID={self.trigger_id} "
                f"Hits={self.num_hits} Mode={self.mode}")

    def print_hits(self):
        """Print detailed hit information"""
        print(self)
        for hit in self.hits:
            print(f"    {hit}")

    def get_hit_by_channel(self, channel):
        """Get hit data for a specific channel (or None if no hit)"""
        for hit in self.hits:
            if hit.channel == channel:
                return hit
        return None
