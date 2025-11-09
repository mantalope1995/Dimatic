// Environment mode types
export enum EnvMode {
  LOCAL = 'local',
  STAGING = 'staging',
  PRODUCTION = 'production',
}

// Subscription tier structure
export interface SubscriptionTierData {
  priceId: string;
  name: string;
}

// Subscription tiers structure
export interface SubscriptionTiers {
  TIER_99: SubscriptionTierData;
  TIER_149: SubscriptionTierData;
  TIER_349: SubscriptionTierData;
  TIER_499: SubscriptionTierData;
}

// Configuration object
interface Config {
  ENV_MODE: EnvMode;
  IS_LOCAL: boolean;
  IS_STAGING: boolean;
  SUBSCRIPTION_TIERS: SubscriptionTiers;
}

// Production tier IDs
const PROD_TIERS: SubscriptionTiers = {
  TIER_99: {
    priceId: 'price_1RILb4G6l1KZGqIrhomjgDnO',
    name: '$99',
  },
  TIER_149: {
    priceId: 'price_1RILb4G6l1KZGqIr5q0sybWn',
    name: '$149',
  },
  TIER_349: {
    priceId: 'price_1RILb4G6l1KZGqIr5Y20ZLHm',
    name: '$349',
  },
  TIER_499: {
    priceId: 'price_1RILb4G6l1KZGqIrGAD8rNjb',
    name: '$499',
  },
} as const;

// Staging tier IDs
const STAGING_TIERS: SubscriptionTiers = {
  TIER_99: {
    priceId: 'price_1RIGvuG6l1KZGqIrCRu0E4Gi',
    name: '$99',
  },
  TIER_149: {
    priceId: 'price_1RIGvuG6l1KZGqIrvjlz5p5V',
    name: '$149',
  },
  TIER_349: {
    priceId: 'price_1RIGvuG6l1KZGqIrT6UfgblC',
    name: '$349',
  },
  TIER_499: {
    priceId: 'price_1RIGvuG6l1KZGqIrOVLKlOMj',
    name: '$499',
  },
} as const;

function getEnvironmentMode(): EnvMode {
  const envMode = (process.env.NEXT_PUBLIC_ENV_MODE || 'local').toUpperCase();
  switch (envMode) {
    case 'LOCAL':
      return EnvMode.LOCAL;
    case 'STAGING':
      return EnvMode.STAGING;
    case 'PRODUCTION':
      return EnvMode.PRODUCTION;
  //   default:
  //     if (process.env.NODE_ENV === 'development') {
  //       return EnvMode.LOCAL;
  //     } else {
  //       return EnvMode.PRODUCTION;
  //     }
  }
}

const currentEnvMode = getEnvironmentMode();

export const config: Config = {
  ENV_MODE: currentEnvMode,
  IS_LOCAL: currentEnvMode === EnvMode.LOCAL,
  IS_STAGING: currentEnvMode === EnvMode.STAGING,
  SUBSCRIPTION_TIERS:
    currentEnvMode === EnvMode.STAGING ? STAGING_TIERS : PROD_TIERS,
};

export const isLocalMode = (): boolean => {
  return config.IS_LOCAL;
};

export const isStagingMode = (): boolean => {
  return config.IS_STAGING;
};


// Remove yearly commitment plans as we're simplifying to 4 tiers only

// Plan type identification functions - simplified for 4-tier structure
export const isMonthlyPlan = (priceId: string): boolean => {
  const allTiers = config.SUBSCRIPTION_TIERS;
  const monthlyTiers = [
    allTiers.TIER_99, allTiers.TIER_149, allTiers.TIER_349, allTiers.TIER_499
  ];
  return monthlyTiers.some(tier => tier.priceId === priceId);
};

export const isYearlyPlan = (priceId: string): boolean => {
  // No yearly plans in the new structure
  return false;
};

// Tier level mappings for simplified 4-tier structure
const PLAN_TIERS = {
  // Production monthly plans
  [PROD_TIERS.TIER_99.priceId]: { tier: 1, type: 'monthly', name: '$99' },
  [PROD_TIERS.TIER_149.priceId]: { tier: 2, type: 'monthly', name: '$149' },
  [PROD_TIERS.TIER_349.priceId]: { tier: 3, type: 'monthly', name: '$349' },
  [PROD_TIERS.TIER_499.priceId]: { tier: 4, type: 'monthly', name: '$499' },

  // Staging monthly plans
  [STAGING_TIERS.TIER_99.priceId]: { tier: 1, type: 'monthly', name: '$99' },
  [STAGING_TIERS.TIER_149.priceId]: { tier: 2, type: 'monthly', name: '$149' },
  [STAGING_TIERS.TIER_349.priceId]: { tier: 3, type: 'monthly', name: '$349' },
  [STAGING_TIERS.TIER_499.priceId]: { tier: 4, type: 'monthly', name: '$499' },
} as const;

export const getPlanInfo = (priceId: string) => {
  return PLAN_TIERS[priceId as keyof typeof PLAN_TIERS] || { tier: 0, type: 'unknown', name: 'Unknown' };
};

// Simplified plan change validation function for 4-tier structure
export const isPlanChangeAllowed = (currentPriceId: string, newPriceId: string): { allowed: boolean; reason?: string } => {
  const currentPlan = getPlanInfo(currentPriceId);
  const newPlan = getPlanInfo(newPriceId);

  // Allow if same plan
  if (currentPriceId === newPriceId) {
    return { allowed: true };
  }

  // Simplified restriction: Don't allow downgrade to lower tier
  if (currentPlan.type === 'monthly' && newPlan.type === 'monthly' && newPlan.tier < currentPlan.tier) {
    return {
      allowed: false,
      reason: 'Downgrading to a lower plan is not allowed. You can only upgrade to a higher tier.'
    };
  }

  // Allow all other changes (upgrades)
  return { allowed: true };
};

// Export subscription tier type for typing elsewhere
export type SubscriptionTier = keyof typeof PROD_TIERS;
