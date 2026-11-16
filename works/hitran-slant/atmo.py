# -*- coding: utf-8 -*-
"""Slant-path transmittance model for an 8 km platform / 20 km ground range.

Geometry
--------
Ground target (z = 0) to platform (z = 8 km, horizontal distance 20 km):
straight-line slant range s = sqrt(20^2 + 8^2) = 21.541 km.
The path is split into layers (denser near the ground, where the air is
thickest); each layer is treated as homogeneous at its mid-point.

Atmosphere (US Standard Atmosphere 1976, troposphere)
-----------------------------------------------------
T(z) = 288.15 - 6.5 z            [K, z in km]
p(z) = 1013.25 (T/288.15)^5.25588 [hPa]
H2O: 7.5 g/m3 at the surface, scale height 2 km (USSA-76 water vapour)
CO2: 415 ppmv (HITRAN2020-era background)
CH4: 1.9 ppmv
"""
import numpy as np

KB = 1.380649e-23
NA = 6.02214076e23
M_H2O = 18.01528  # g/mol

Z_PLATFORM = 8.0   # km
X_GROUND = 20.0    # km
X_CO2 = 415e-6
X_CH4 = 1.9e-6


def ussa76(z_km):
    z = np.asarray(z_km, dtype=float)
    T = 288.15 - 6.5 * z
    p = 1013.25 * (T / 288.15) ** 5.25588
    return T, p


def h2o_density_gm3(z_km):
    return 7.5 * np.exp(-np.asarray(z_km, dtype=float) / 2.0)


def build_layers(nlayers=24):
    """Return dict of layer mid-point properties and slant path lengths."""
    u = np.linspace(0.0, 1.0, nlayers + 1)
    z_edges = Z_PLATFORM * u ** 1.5        # finer spacing near the ground
    z_mid = 0.5 * (z_edges[1:] + z_edges[:-1])
    dz = np.diff(z_edges)
    ratio = X_GROUND / Z_PLATFORM
    ds_km = dz * np.sqrt(1.0 + ratio ** 2)  # slant length of each layer
    T, p_hpa = ussa76(z_mid)
    p_pa = p_hpa * 100.0
    n_air = p_pa / (KB * T) / 1e6            # molecules / cm^3
    rho_w = h2o_density_gm3(z_mid)           # g/m^3
    n_h2o = rho_w / M_H2O * NA / 1e6         # molecules / cm^3
    return dict(z=z_mid, z_edges=z_edges, ds_cm=ds_km * 1e5, T=T, p_hpa=p_hpa,
                p_atm=p_hpa / 1013.25, n_air=n_air, n_h2o=n_h2o,
                n_co2=X_CO2 * n_air, n_ch4=X_CH4 * n_air,
                x_h2o=n_h2o / n_air,
                x_co2=np.full_like(n_air, X_CO2),
                x_ch4=np.full_like(n_air, X_CH4))


def path_summary(layers):
    return dict(s_total_km=float(np.sqrt(X_GROUND ** 2 + Z_PLATFORM ** 2)),
                z_layers=layers['z'], ds_km=layers['ds_cm'] / 1e5,
                T=layers['T'], p_hpa=layers['p_hpa'],
                n_h2o=layers['n_h2o'], n_co2=layers['n_co2'],
                n_ch4=layers['n_ch4'])
