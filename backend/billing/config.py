from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass
from core.utils.config import config

TRIAL_ENABLED = True
TRIAL_DURATION_DAYS = 7
TRIAL_TIER = "tier_2_20"
TRIAL_CREDITS = Decimal("5.00")

TOKEN_PRICE_MULTIPLIER = Decimal('1.2')
MINIMUM_CREDIT_FOR_RUN = Decimal('0.01')
DEFAULT_TOKEN_COST = Decimal('0.000002')

FREE_TIER_INITIAL_CREDITS = Decimal('5.00')

@dataclass
class Tier:
    name: str
    price_ids: List[str]
    monthly_credits: Decimal
    display_name: str
    can_purchase_credits: bool
    models: List[str]
    project_limit: int

TIERS: Dict[str, Tier] = {
    'none': Tier(
        name='none',
        price_ids=[],
        monthly_credits=Decimal('0.00'),
        display_name='No Plan',
        can_purchase_credits=False,
        models=[],
        project_limit=0
    ),
    'free': Tier(
        name='free',
        price_ids=[],
        monthly_credits=Decimal('0.00'),
        display_name='Free Tier (Discontinued)',
        can_purchase_credits=False,
        models=[],
        project_limit=0
    ),
    'tier_99': Tier(
        name='tier_99',
        price_ids=[
            config.STRIPE_TIER_99_ID,
        ],
        monthly_credits=Decimal('99.00'),
        display_name='Starter',
        can_purchase_credits=False,
        models=['all'],
        project_limit=500
    ),
    'tier_149': Tier(
        name='tier_149',
        price_ids=[
            config.STRIPE_TIER_149_ID,
        ],
        monthly_credits=Decimal('149.00'),
        display_name='Professional',
        can_purchase_credits=False,
        models=['all'],
        project_limit=2000
    ),
    'tier_349': Tier(
        name='tier_349',
        price_ids=[
            config.STRIPE_TIER_349_ID,
        ],
        monthly_credits=Decimal('349.00'),
        display_name='Business',
        can_purchase_credits=False,
        models=['all'],
        project_limit=10000
    ),
    'tier_499': Tier(
        name='tier_499',
        price_ids=[
            config.STRIPE_TIER_499_ID,
        ],
        monthly_credits=Decimal('499.00'),
        display_name='Enterprise',
        can_purchase_credits=True,
        models=['all'],
        project_limit=25000
    ),
}

CREDIT_PACKAGES = [
    {'amount': Decimal('10.00'), 'stripe_price_id': config.STRIPE_CREDITS_10_PRICE_ID},
    {'amount': Decimal('25.00'), 'stripe_price_id': config.STRIPE_CREDITS_25_PRICE_ID},
    {'amount': Decimal('50.00'), 'stripe_price_id': config.STRIPE_CREDITS_50_PRICE_ID},
    {'amount': Decimal('100.00'), 'stripe_price_id': config.STRIPE_CREDITS_100_PRICE_ID},
    {'amount': Decimal('250.00'), 'stripe_price_id': config.STRIPE_CREDITS_250_PRICE_ID},
    {'amount': Decimal('500.00'), 'stripe_price_id': config.STRIPE_CREDITS_500_PRICE_ID},
]

ADMIN_LIMITS = {
    'max_credit_adjustment': Decimal('1000.00'),
    'max_bulk_grant': Decimal('10000.00'),
    'require_super_admin_above': Decimal('500.00'),
}

def get_tier_by_price_id(price_id: str) -> Optional[Tier]:
    for tier in TIERS.values():
        if price_id in tier.price_ids:
            return tier
    return None

def get_tier_by_name(tier_name: str) -> Optional[Tier]:
    return TIERS.get(tier_name)

def get_monthly_credits(tier_name: str) -> Decimal:
    tier = TIERS.get(tier_name)
    return tier.monthly_credits if tier else TIERS['none'].monthly_credits

def can_purchase_credits(tier_name: str) -> bool:
    tier = TIERS.get(tier_name)
    return tier.can_purchase_credits if tier else False

def is_model_allowed(tier_name: str, model: str) -> bool:
    tier = TIERS.get(tier_name, TIERS['none'])
    if 'all' in tier.models:
        return True
    return model in tier.models

def get_project_limit(tier_name: str) -> int:
    tier = TIERS.get(tier_name)
    return tier.project_limit if tier else 3 