'use client';

import { SectionHeader } from '@/components/home/section-header';
import { motion, useInView } from 'framer-motion';
import { useRef } from 'react';
import {
  FileText,
  Image,
  Presentation,
  Globe,
  BarChart3,
  ShoppingCart,
  Users,
  Clock,
  AlertTriangle,
  DollarSign,
  TrendingUp
} from 'lucide-react';

const capabilities = [
  {
    title: 'Identify Dead Stock & Slow Movers',
    description: 'Automatically analyse your inventory to find products tying up your cash. Get clear reports on what to discount, bundle, or discontinue to free up working capital.',
    icon: <BarChart3 className="size-6" />,
  },
  {
    title: 'Predict Stockouts Before They Happen',
    description: 'Analyse sales velocity and trends to forecast when you will run out of bestsellers. Stop losing revenue to preventable stockouts.',
    icon: <AlertTriangle className="size-6" />,
  },
  {
    title: 'Automate Stock Reconciliation',
    description: 'Connect your sales channels and automatically reconcile inventory levels. No more weekend spreadsheet marathons or manual data entry.',
    icon: <FileText className="size-6" />,
  },
  {
    title: 'Track Real Profitability Per SKU',
    description: 'Go beyond revenue to see which products actually make you money after accounting for carrying costs, slow turnover, and margins.',
    icon: <DollarSign className="size-6" />,
  },
  {
    title: 'Monitor Competitor Pricing',
    description: 'Automatically track competitor prices across multiple channels. Make data-driven pricing decisions instead of guessing.',
    icon: <Globe className="size-6" />,
  },
  {
    title: 'Generate Reorder Alerts',
    description: 'Get automatic notifications when stock levels hit critical thresholds. Move from reactive panic ordering to strategic purchasing.',
    icon: <ShoppingCart className="size-6" />,
  },
  {
    title: 'Analyse Sales Patterns & Trends',
    description: 'Upload your sales data and discover seasonal patterns, trending products, and hidden opportunities you are missing in your spreadsheets.',
    icon: <TrendingUp className="size-6" />,
  },
  {
    title: 'Work Around the Clock',
    description: 'Schedule daily stock audits, weekly dead stock reports, and automatic price checks to run while you sleep. Reclaim your 15-20 hours per week.',
    icon: <Clock className="size-6" />,
  },
];

export function CapabilitiesSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-10%" });

  return (
    <section
      id="capabilities"
      className="flex flex-col items-center justify-center w-full relative"
      ref={ref}
    >
      <div className="relative w-full px-6">
        <div className="max-w-6xl mx-auto border-l border-r border-border">
          <SectionHeader>
            <h2 className="text-3xl md:text-4xl font-medium tracking-tighter text-center text-balance pb-1">
              What Can Dimatic Do For You?
            </h2>
            <p className="text-muted-foreground text-center text-balance font-medium">
              From stock reconciliation to profitability analysis, Dimatic automates the manual inventory work that's stealing your time—so you can focus on growing your business.
            </p>
          </SectionHeader>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 border-t border-border">
            {capabilities.map((capability, index) => (
              <motion.div
                key={capability.title}
                initial={{ opacity: 0, y: 20 }}
                animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
                transition={{
                  duration: 0.5,
                  delay: index * 0.1,
                  ease: 'easeOut',
                }}
                className="relative p-6 border-border group hover:bg-accent/5 transition-colors duration-300 [&:not(:nth-child(4n))]:border-r [&:not(:nth-last-child(-n+4))]:border-b"
              >
                {/* Icon */}
                <div className="flex items-center justify-center size-12 bg-secondary/10 rounded-xl mb-4 group-hover:bg-secondary/20 transition-colors duration-300">
                  <div className="text-secondary">
                    {capability.icon}
                  </div>
                </div>

                {/* Content */}
                <div className="space-y-2">
                  <h3 className="text-lg font-semibold tracking-tight">
                    {capability.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {capability.description}
                  </p>
                </div>

              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
