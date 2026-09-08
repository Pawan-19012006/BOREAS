"""Honest connectivity status for the frontend's live satellite tile strip.

See boreas_core/satellite/status.py -- this exists because sentinel-1,
sentinel-2, and copernicus-marine's frontend layer sources previously
hardcoded `getStatus(): 'LIVE'` while actually fetching different NASA/JAXA
GIBS layers mislabeled with ESA/Copernicus credit text. This module is the
real, env-var-gated check the frontend now calls instead.
"""
