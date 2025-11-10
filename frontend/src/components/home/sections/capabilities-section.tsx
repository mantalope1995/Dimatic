'use client';

import { SectionHeader } from '@/components/home/section-header';
import { motion, useInView } from 'motion/react';
import { useRef } from 'react';
import {
  FileText,
  Globe,
  BarChart3,
  ShoppingCart,
  Users,
  Clock,
  Network,
  ShieldCheck
} from 'lucide-react';

const capabilities = [
  {
    title: 'Find Your Hidden Profits',
    description: 'Stop guessing. Upload your existing Excel or Google Sheet  and instantly find the cash trapped in dead stock, spot your stockout risks, and see what to reorder based on data, not gut feel.',
    icon: <BarChart3 className="size-6" />,
  },
  {
    title: 'Reclaim Your 15-20 Hours/Week',
    description: 'Stop manually reconciling sales logs, updating stock sheets, or cross-referencing data. Automate the repetitive admin that is killing your week and stifling your growth.',
    icon: <ShoppingCart className="size-6" />, // Changed from original to better fit inventory
  },
  {
    title: 'Get Real-Time Low-Stock Alerts',
    description: 'Never lose a major sale to a preventable stockout again. Get automatic alerts on your high-turnover items before you run out, based on your real sales velocity.',
    icon: <Users className="size-6" />, // Changed from original
  },
  {
    title: 'Run Stock Audits Overnight',
    description: 'Why spend a weekend manually reconciling spreadsheets for tax time? Schedule your inventory audits and sales reconciliations to run while you sleep.',
    icon: <Clock className="size-6" />,
  },
  {
    title: 'Monitor Competitor & Supplier Pricing',
    description: 'Get comprehensive, automated reports on competitor price changes and supplier delays. Stop making reactive purchasing decisions and get ahead of supply chain issues.',
    icon: <Globe className="size-6" />,
  },
  {
    title: 'Generate Instant Stock Reports',
    description: 'Turn your messy spreadsheets into clean, daily reports  that show sales velocity, profitability per SKU, and inventory accuracy. No IT team or developer needed.',
    icon: <FileText className="size-6" />,
  },
  {
    title: 'Sync Your Multi-Channel Sales',
    description: 'Stop the chaos of selling on 2+ channels. Connect your e-commerce site, online marketplace, and sales logs to one central, real-time inventory. End overselling and get your inventory accuracy back.',
    icon: <Network className="size-6" />, 
  },
  {
    title: 'Create a Single Source of Truth',
    description: 'That massive, complex spreadsheet is your single biggest bottleneck. Turn its chaos into a simple, trustworthy dashboard your entire team can use, making your system teachable for new employees.',
    icon: <ShieldCheck className="size-6" />,
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
              From content creation to data analysis, Dimatic handles the work that takes you hours in just minutes.
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
