'use client';

import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { UpgradeDialog } from '@/components/ui/upgrade-dialog';
import { PricingSection } from '@/components/home/sections/pricing-section';

interface AgentCountLimitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentCount: number;
  limit: number;
  tierName: string;
}

export const AgentCountLimitDialog: React.FC<AgentCountLimitDialogProps> = ({
  open,
  onOpenChange,
  currentCount,
  limit,
  tierName,
}) => {
  const returnUrl = typeof window !== 'undefined' ? window.location.href : '/';

  const getNextTierRecommendation = () => {
    if (tierName === 'free' || tierName === 'none') {
      return {
        name: 'Starter',
        price: '$99/month',
        agentLimit: 5,
      };
    } else if (tierName.includes('tier_99')) {
      return {
        name: 'Professional',
        price: '$149/month',
        agentLimit: 15,
      };
    } else if (tierName.includes('tier_149')) {
      return {
        name: 'Business',
        price: '$349/month',
        agentLimit: 50,
      };
    } else if (tierName.includes('tier_349')) {
      return {
        name: 'Enterprise',
        price: '$499/month',
        agentLimit: 100,
      };
    }
    return null;
  };

  const nextTier = getNextTierRecommendation();

  return (
    <UpgradeDialog
      open={open}
      onOpenChange={onOpenChange}
      icon={AlertTriangle}
      title="Agent Limit Reached"
      description="You've reached the maximum number of agents allowed on your current plan."
      theme="warning"
      size="xl"
      className="[&_.grid]:!grid-cols-4 [&_.grid]:gap-3 mt-8"
    >
      <PricingSection 
        returnUrl={returnUrl} 
        showTitleAndTabs={false} 
        insideDialog={true} 
        showInfo={false}
        noPadding={true}
      />
    </UpgradeDialog>
  );
}; 