"""Verified native Aqueduct4.0 temporal identities shared across components.

Source: WRI's Understanding Future Projections help page. These are trend
windows and five-model medians, never individual-year climate observations.
"""
AQUEDUCT_WINDOWS = {2030: (2015, 2045), 2050: (2035, 2065), 2080: (2065, 2095)}
AQUEDUCT_PATHWAYS = {'bau': 'SSP3-RCP7.0', 'opt': 'SSP1-RCP2.6', 'pes': 'SSP5-RCP8.5'}
AQUEDUCT_GCMS = ['GFDL-ESM4', 'IPSL-CM6A-LR', 'MPI-ESM1-2-HR', 'MRI-ESM2-0', 'UKESM1-0-LL']
AQUEDUCT_MODEL = 'HYPFLOWSCI6; five-GCM median'
AQUEDUCT_PERIOD_VERSION = 'aqueduct4.0-native-future-windows-v1'
