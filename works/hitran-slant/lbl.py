# -*- coding: utf-8 -*-
"""Line-by-line absorption cross sections from HITRAN2020 line parameters.

Physics
-------
* Voigt line shape (Doppler + Lorentz), HITRAN air-broadening parameters,
  pressure shift, temperature dependence of line intensity (TIPS partition
  functions) and of the Lorentz half width.
* Natural isotopologue abundances are applied, so sigma is per molecule of
  the parent gas (H2O, CO2, CH4).
* Line wings are truncated at 25 / 12 / 6 cm-1 depending on reference line
  intensity (weak lines cannot contribute appreciable absorption in the far
  wings over a ~20 km path).
* Weak lines are evaluated on a coarser sub-grid and interpolated, which
  speeds the calculation up several times without visible spectral change.
"""
import numpy as np
from scipy.special import wofz

C2 = 1.438776877          # hc/k  [cm K]
KB = 1.380649e-23         # J/K
C_CM = 2.99792458e10      # cm/s
AMU = 1.66053906660e-27   # kg
SQPI = np.sqrt(np.pi)

WING_STRONG = 25.0        # cm^-1
WING_MED = 12.0
WING_WEAK = 6.0
S_STRONG = 1.0e-22        # cm^-1/(molecule cm^-2) at 296 K
S_MED = 1.0e-25
S_MIN = 1.0e-28

COARSE_FACTOR = 5         # weak lines: evaluate every 5th grid point
S_COARSE = 3.0e-25


class MolLines:
    """Line parameters of one molecule (all isotopologues)."""

    def __init__(self, path, molecule_id, iso_table, partition_sum):
        d = np.load(path)
        iso = d['iso'].astype(int)
        nu, sw = d['nu'], d['sw']
        gair, gself = d['gair'], d['gself']
        elower, nair, delta = d['elower'], d['nair'], d['delta']

        keep = (sw >= S_MIN) & np.isfinite(nu) & np.isfinite(sw) & (iso >= 1)
        iso, nu, sw = iso[keep], nu[keep], sw[keep]
        gair, gself = gair[keep], gself[keep]
        elower, nair, delta = elower[keep], nair[keep], delta[keep]

        self.M = molecule_id
        self.iso = iso
        self.nu = nu
        self.sw = sw
        self.gair = np.maximum(gair, 1.0e-4)
        self.gself = np.maximum(gself, 1.0e-4)
        self.elower = elower
        self.nair = nair
        self.delta = delta

        uniq = np.unique(iso)
        self.iso_uniq = uniq
        self.iso_map = np.searchsorted(uniq, iso)
        self.abund = np.array([iso_table[(molecule_id, i)][2] for i in uniq])[self.iso_map]
        self.mass = np.array([iso_table[(molecule_id, i)][3] for i in uniq])[self.iso_map] * AMU
        self.q296 = np.array([partition_sum(molecule_id, i, 296.0) for i in uniq])[self.iso_map]

        self.half = np.where(sw >= S_STRONG, WING_STRONG,
                             np.where(sw >= S_MED, WING_MED, WING_WEAK))
        self.coarse = sw < S_COARSE

    def sigma(self, T, p_atm, x_self, grid, step, qT_iso):
        """Absorption cross section [cm^2/molecule] on `grid` (cm^-1)."""
        ng = grid.size
        sigma = np.zeros(ng)
        qT = qT_iso[self.iso_map]

        boltz = np.exp(-C2 * self.elower * (1.0 / T - 1.0 / 296.0))
        stim = ((1.0 - np.exp(-C2 * self.nu / T))
                / (1.0 - np.exp(-C2 * self.nu / 296.0)))
        sT = self.sw * (self.q296 / qT) * boltz * stim * self.abund

        p_self = p_atm * x_self
        gl = ((296.0 / T) ** self.nair
              * (self.gair * (p_atm - p_self) + self.gself * p_self))
        gl = np.maximum(gl, 1.0e-6)
        gd = (self.nu / C_CM) * np.sqrt(2.0 * KB * T / self.mass)
        gd = np.maximum(gd, 1.0e-8)
        nus = self.nu + self.delta * p_atm

        # only lines whose truncated profile overlaps the grid
        sel = (nus + self.half > grid[0]) & (nus - self.half < grid[-1])
        if not sel.all():
            nus, gl, gd, sT = nus[sel], gl[sel], gd[sel], sT[sel]
            half, coarse = self.half[sel], self.coarse[sel]
        else:
            half, coarse = self.half, self.coarse

        g0 = grid[0]
        for i in range(nus.size):
            c = nus[i]
            hw = half[i]
            lo = int((c - hw - g0) / step)
            hi = int((c + hw - g0) / step) + 2
            if lo < 0:
                lo = 0
            if hi > ng:
                hi = ng
            if hi <= lo:
                continue
            y = gl[i] / gd[i]
            if coarse[i]:
                sl = slice(lo, hi, COARSE_FACTOR)
                xs = grid[sl]
                f = wofz((xs - c) / gd[i] + 1j * y).real * (1.0 / (gd[i] * SQPI))
                sig = np.interp(grid[lo:hi], xs, f)
                sigma[lo:hi] += sT[i] * sig
            else:
                f = wofz((grid[lo:hi] - c) / gd[i] + 1j * y).real * (1.0 / (gd[i] * SQPI))
                sigma[lo:hi] += sT[i] * f
        return sigma
