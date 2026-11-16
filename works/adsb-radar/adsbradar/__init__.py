"""adsb-radar: RTL-SDR ADS-B receiver + radar-style PPI display.

A self-contained ADS-B (Mode S 1090ES) decoder and local web radar for the
RTL-SDR Blog V4 dongle. Sources: direct IQ demodulation via pyrtlsdr, the
``rtl_adsb`` helper, a remote dump1090/readsb server, or a built-in simulator.
"""

__version__ = "0.1.0"
