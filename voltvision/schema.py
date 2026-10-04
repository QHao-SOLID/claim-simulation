"""Structural schema — the parts the system must know by shape (never by value).

What lives here:
  COLS  canonical simulated-book column order (attributes + claims only)

Everything numeric lives in base_template.json (simulation assumptions).
This file holds no assumptions and no premium columns: the simulator is
premium-independent.
"""

# Canonical simulated-book column order (simulate.py output). Result files
# (CSV) carry exactly these columns — never a premium column.
COLS = ['POLID', 'COVERAGE_TYPE', 'SUM_ASSURED', 'REGION', 'VEHICLE_TYPE',
        'ENGINE_CAPACITY',
        'DRIVER_AGE_CAT', 'DRIVER_AGE', 'CAR_AGE', 'DRIVER_GENDER',
        'FLOOD_RISK', 'THEFT_RISK', 'FLOOD_EVENT_YEAR',
        'NCD_LEVEL_PRICED', 'NCD_LEVEL',
        'NCD_YEARS', 'CLAIM_LAMBDA',
        'SIM_YEAR', 'CLAIM_COUNT', 'CLAIM_OCCURRED', 'CLAIM_AMOUNT',
        'CLAIM_PERIL',
        'RENEWAL_PROB', 'RENEWED', 'COHORT_YEAR',
        'BEHAVIOR_RISK',
        'telematics_hard_braking', 'telematics_speeding', 'telematics_night_share',
        'telematics_blend', 'telematics_score', 'telematics_rank_pct']

# Claim-level detail (one row per claim), written beside the policy-year CSV.
CLAIM_COLS = ['POLID', 'SIM_YEAR', 'COHORT_YEAR', 'COVERAGE_TYPE', 'VEHICLE_TYPE',
              'DRIVER_AGE_CAT', 'CLAIM_PERIL', 'SUM_ASSURED', 'RAW_GAMMA', 'CAP',
              'TOTAL_LOSS', 'EXCESS_APPLIED', 'INFLATION_FACTOR',
              'SETTLED_PAYOUT']
