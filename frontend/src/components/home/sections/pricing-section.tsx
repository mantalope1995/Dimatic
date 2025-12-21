'use client';

import { SectionHeader } from '@/components/home/section-header';
import { siteConfig } from '@/lib/home';
import { cn } from '@/lib/utils';
import { motion } from 'motion/react';
import React, { useState } from 'react';
import {
  CheckIcon,
  Clock,
  Bot,
  FileText,
  Settings,
  Grid3X3,
  Diamond,
  Heart,
  Zap
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

// App URL for CTA buttons
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://app.suna.so';

// Feature icon mapping
const getFeatureIcon = (feature: string) => {
  const featureLower = feature.toLowerCase();

  if (featureLower.includes('token credits') || featureLower.includes('ai token')) {
    return <Clock className="size-4" />;
  }
  if (featureLower.includes('custom agents') || featureLower.includes('agents')) {
    return <Bot className="size-4" />;
  }
  if (featureLower.includes('private projects') || featureLower.includes('public projects')) {
    return <FileText className="size-4" />;
  }
  if (featureLower.includes('custom abilities') || featureLower.includes('basic abilities')) {
    return <Settings className="size-4" />;
  }
  if (featureLower.includes('integrations') || featureLower.includes('100+')) {
    return <Grid3X3 className="size-4" />;
  }
  if (featureLower.includes('premium ai models')) {
    return <Diamond className="size-4" />;
  }
  if (featureLower.includes('community support') || featureLower.includes('priority support')) {
    return <Heart className="size-4" />;
  }
  if (featureLower.includes('dedicated account manager')) {
    return <Zap className="size-4" />;
  }

  return <CheckIcon className="size-4" />;
};

interface PriceDisplayProps {
  price: string;
  isCompact?: boolean;
}

function PriceDisplay({ price, isCompact }: PriceDisplayProps) {
  return (
    <motion.span
      key={price}
      className={isCompact ? 'text-xl font-semibold' : 'text-4xl font-semibold'}
      initial={{
        opacity: 0,
        x: 10,
        filter: 'blur(5px)',
      }}
      animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
    >
      {price}
    </motion.span>
  );
}

function BillingPeriodToggle({
  billingPeriod,
  setBillingPeriod
}: {
  billingPeriod: 'monthly' | 'yearly';
  setBillingPeriod: (period: 'monthly' | 'yearly') => void;
}) {
  return (
    <div className="flex items-center justify-center gap-3">
      <div className="relative bg-muted rounded-full p-1">
        <div className="flex">
          <div
            className={cn("px-3 py-1 rounded-full text-xs font-medium transition-all duration-200 cursor-pointer",
              billingPeriod === 'monthly'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={() => setBillingPeriod('monthly')}
          >
            Monthly
          </div>
          <div
            className={cn("px-3 py-1 rounded-full text-xs font-medium transition-all duration-200 flex items-center gap-1 cursor-pointer",
              billingPeriod === 'yearly'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={() => setBillingPeriod('yearly')}
          >
            Yearly
            <span className="bg-green-600 text-green-50 dark:bg-green-500 dark:text-green-50 text-[10px] px-1.5 py-0.5 rounded-full font-semibold whitespace-nowrap">
              15% off
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

interface StaticPricingTierProps {
  tier: typeof siteConfig.cloudPricingItems[0];
  billingPeriod: 'monthly' | 'yearly';
}

function StaticPricingTier({ tier, billingPeriod }: StaticPricingTierProps) {
  // Calculate display price based on billing period
  const getDisplayPrice = () => {
    if (billingPeriod === 'yearly') {
      const regularPrice = parseFloat(tier.price.slice(1));
      const discountedPrice = Math.round(regularPrice * 0.85);
      return `$${discountedPrice}`;
    }
    return tier.price;
  };

  const displayPrice = getDisplayPrice();

  return (
    <div
      className={cn(
        'rounded-xl flex flex-col relative h-full min-h-[300px]',
        tier.isPopular
          ? 'md:shadow-[0px_61px_24px_-10px_rgba(0,0,0,0.01),0px_34px_20px_-8px_rgba(0,0,0,0.05),0px_15px_15px_-6px_rgba(0,0,0,0.09),0px_4px_8px_-2px_rgba(0,0,0,0.10),0px_0px_0px_1px_rgba(0,0,0,0.08)] bg-accent'
          : 'bg-[#F3F4F6] dark:bg-[#F9FAFB]/[0.02] border border-border',
      )}
    >
      <div className="flex flex-col gap-3 p-4">
        <p className="text-sm flex items-center gap-2">
          {tier.name}
          {tier.isPopular && (
            <span className="bg-gradient-to-b from-secondary/50 from-[1.92%] to-secondary to-[100%] text-white inline-flex w-fit items-center justify-center px-1.5 py-0.5 rounded-full text-[10px] font-medium shadow-[0px_6px_6px_-3px_rgba(0,0,0,0.08),0px_3px_3px_-1.5px_rgba(0,0,0,0.08),0px_1px_1px_-0.5px_rgba(0,0,0,0.08),0px_0px_0px_1px_rgba(255,255,255,0.12)_inset,0px_1px_0px_0px_rgba(255,255,255,0.12)_inset]">
              Popular
            </span>
          )}
        </p>
        <div className="flex items-baseline mt-2">
          {billingPeriod === 'yearly' ? (
            <div className="flex flex-col">
              <div className="flex items-baseline gap-2">
                <PriceDisplay price={displayPrice} />
                <span className="text-xs line-through text-muted-foreground">
                  {tier.price}
                </span>
              </div>
              <div className="flex items-center gap-1 mt-1">
                <span className="text-xs text-muted-foreground">/month</span>
                <span className="text-xs text-muted-foreground">billed yearly</span>
              </div>
            </div>
          ) : (
            <div className="flex items-baseline">
              <PriceDisplay price={displayPrice} />
              <span className="ml-2">/month</span>
            </div>
          )}
        </div>

        {billingPeriod === 'yearly' && (
          <div className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold bg-green-50 border-green-200 text-green-700 w-fit">
            Save ${Math.round(parseFloat(tier.price.slice(1)) * 0.15 * 12)} per year
          </div>
        )}
      </div>

      <div className="flex-grow px-4 pb-3">
        {tier.features && tier.features.length > 0 && (
          <ul className="space-y-3">
            {tier.features.map((feature) => (
              <li key={feature} className="flex items-center gap-3">
                <div className="size-5 min-w-5 flex items-center justify-center text-muted-foreground">
                  {getFeatureIcon(feature)}
                </div>
                <span className="text-sm">{feature}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-auto px-4 pt-2 pb-4">
        <Link href={`${APP_URL}/auth?mode=signup`}>
          <Button
            className={cn(
              'w-full font-medium transition-all duration-200 h-10 rounded-full text-sm',
              tier.isPopular
                ? 'bg-primary hover:bg-primary/90 text-primary-foreground'
                : 'bg-secondary hover:bg-secondary/90 text-white'
            )}
          >
            Get Started
          </Button>
        </Link>
      </div>
    </div>
  );
}

interface PricingSectionProps {
  showTitleAndTabs?: boolean;
  showInfo?: boolean;
  noPadding?: boolean;
}

export function PricingSection({
  showTitleAndTabs = true,
  showInfo = true,
  noPadding = false,
}: PricingSectionProps) {
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('yearly');

  return (
    <section
      id="pricing"
      className={cn("flex flex-col items-center justify-center gap-10 w-full relative", noPadding ? "pb-0" : "pb-12")}
    >
      <div className="w-full max-w-6xl mx-auto px-6">
        {showTitleAndTabs && (
          <SectionHeader>
            <h2 className="text-3xl md:text-4xl font-medium tracking-tighter text-center text-balance">
              Choose the right plan for your needs
            </h2>
            <p className="text-muted-foreground text-center text-balance font-medium">
              Start with our free plan or upgrade for more AI token credits
            </p>
          </SectionHeader>
        )}

        <div className="flex justify-center mb-8">
          <BillingPeriodToggle
            billingPeriod={billingPeriod}
            setBillingPeriod={setBillingPeriod}
          />
        </div>

        <div className="grid gap-6 w-full min-[650px]:grid-cols-2 lg:grid-cols-3 grid-rows-1 items-stretch">
          {siteConfig.cloudPricingItems
            .filter((tier) => !tier.hidden)
            .map((tier) => (
              <StaticPricingTier
                key={tier.name}
                tier={tier}
                billingPeriod={billingPeriod}
              />
            ))}
        </div>
      </div>
      {showInfo && (
        <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg max-w-2xl mx-auto">
          <p className="text-sm text-blue-800 dark:text-blue-200 text-center">
            <strong>What are AI tokens?</strong> Tokens are units of text that AI models process.
            Your plan includes credits to spend on various AI models - the more complex the task,
            the more tokens used.
          </p>
        </div>
      )}
    </section>
  );
}
