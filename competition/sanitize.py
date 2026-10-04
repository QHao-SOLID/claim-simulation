"""Public-vs-hidden column whitelists (leak guard).

Forbidden in any public dataset:
  CLAIM_LAMBDA   exact expected claim rate (hidden truth)
  BEHAVIOR_RISK  latent risk driver
  RAW_GAMMA      pre-cap severity draw (settlement internals)
  CAP            severity cap rule internals
"""

from voltvision.schema import CLAIM_COLS

# Never shipped in public workbooks.
FORBIDDEN_PUBLIC_COLS = {'CLAIM_LAMBDA', 'BEHAVIOR_RISK', 'RAW_GAMMA', 'CAP'}

TELEMATICS_COLS = ['telematics_hard_braking', 'telematics_speeding',
                   'telematics_night_share', 'telematics_blend',
                   'telematics_score', 'telematics_rank_pct']

ATTR_COLS = ['POLID', 'SIM_YEAR', 'COHORT_YEAR', 'COVERAGE_TYPE', 'SUM_ASSURED',
             'REGION', 'VEHICLE_TYPE', 'ENGINE_CAPACITY',
             'DRIVER_AGE_CAT', 'DRIVER_AGE', 'CAR_AGE', 'DRIVER_GENDER',
             'FLOOD_RISK', 'THEFT_RISK', 'NCD_LEVEL', 'NCD_YEARS'] + TELEMATICS_COLS

# Policy-year sheet shipped for TRAIN seasons: attributes + observed outcomes.
TRAIN_POLICY_COLS = ATTR_COLS + ['FLOOD_EVENT_YEAR', 'NCD_LEVEL_PRICED',
                                 'CLAIM_COUNT', 'CLAIM_OCCURRED',
                                 'CLAIM_AMOUNT', 'CLAIM_PERIL']

# Policy-year sheet shipped for TEST seasons: pricing-time information only.
# No claim outcomes, no event markers, no churn.
TEST_POLICY_COLS = ['TEST_ID'] + ATTR_COLS

# Claim-level sheet shipped for TRAIN seasons (settlement internals removed).
TRAIN_CLAIM_COLS = [c for c in CLAIM_COLS if c not in ('RAW_GAMMA', 'CAP')]


def check_public_columns(columns, context):
    """Fail loud if a public frame would leak a forbidden column."""
    leaked = FORBIDDEN_PUBLIC_COLS.intersection(columns)
    if leaked:
        raise ValueError(f'{context}: forbidden column(s) in public data: {sorted(leaked)}')
    return columns
