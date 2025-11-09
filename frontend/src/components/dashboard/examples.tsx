'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import {
  BarChart3,
  Bot,
  Briefcase,
  Settings,
  Sparkles,
  RefreshCw,
  TrendingUp,
  Users,
  Shield,
  Zap,
  Target,
  Brain,
  Globe,
  Heart,
  PenTool,
  Code,
  Camera,
  Calendar,
  DollarSign,
  Rocket,
} from 'lucide-react';

type PromptExample = {
  title: string;
  query: string;
  icon: React.ReactNode;
};

const allPrompts: PromptExample[] = [
  {
    title: 'Automate inventory tracking',
    query: '1. Review the Excel inventory spreadsheets from multiple warehouse locations\n2. Clean and standardise product codes, SKUs, and quantities across systems\n3. Calculate current stock levels, safety stock, and reorder points\n4. Generate automated low-stock alerts and purchase order recommendations\n5. Create real-time inventory dashboard with turnover metrics',
    icon: <BarChart3 className="text-blue-700 dark:text-blue-400" size={16} />,
  },
  {
    title: 'Optimise warehouse operations',
    query: '1. Analyse current warehouse layout and storage utilisation rates\n2. Map product movement patterns and picking frequency data\n3. Calculate optimal slotting based on velocity, size, and weight\n4. Design new layout with improved picking routes and workflow\n5. Generate implementation plan with ROI and productivity gains',
    icon: <Target className="text-cyan-700 dark:text-cyan-400" size={16} />,
  },
  {
    title: 'Manage multi-location inventory',
    query: '1. Consolidate inventory data from multiple stores and warehouses\n2. Analyse stock distribution and identify transfer opportunities\n3. Calculate optimal inventory allocation across locations\n4. Generate automated stock transfer orders and balancing recommendations\n5. Create location performance comparison reports',
    icon: <RefreshCw className="text-rose-700 dark:text-rose-400" size={16} />,
  },
  {
    title: 'Automate stock reconciliation',
    query: '1. Review the physical count sheets from multiple warehouse locations\n2. Compare with system inventory records and identify discrepancies\n3. Calculate shrinkage rates by category and location\n4. Generate adjustment journals and update system records\n5. Create variance analysis reports with root cause recommendations',
    icon: <Shield className="text-indigo-700 dark:text-indigo-400" size={16} />,
  },
  {
    title: 'Optimise picking efficiency',
    query: '1. Analyse order patterns and picking data from warehouse system\n2. Identify bottlenecks and inefficiencies in current picking process\n3. Calculate optimal picking routes and batch grouping strategies\n4. Generate improved pick lists with zone and wave picking\n5. Create productivity tracking and performance metrics',
    icon: <TrendingUp className="text-purple-700 dark:text-purple-400" size={16} />,
  },
  {
    title: 'Manage supplier deliveries',
    query: '1. Track incoming deliveries from multiple suppliers and locations\n2. Analyse on-time delivery rates and quality inspection results\n3. Calculate supplier performance scores and reliability metrics\n4. Generate automated delivery scheduling and receiving workflows\n5. Create supplier performance comparison reports',
    icon: <Briefcase className="text-teal-700 dark:text-teal-400" size={16} />,
  },
  {
    title: 'Forecast inventory demand',
    query: '1. Review the historical sales data and seasonal trend analysis\n2. Analyse demand patterns by product, category, and location\n3. Apply forecasting models for 3-6 month inventory projections\n4. Calculate safety stock levels and optimal order quantities\n5. Generate automated demand planning and purchasing recommendations',
    icon: <Calendar className="text-violet-700 dark:text-violet-400" size={16} />,
  },
  {
    title: 'Automate order fulfillment',
    query: '1. Review orders from multiple sales channels (web, phone, email)\n2. Validate inventory availability across all warehouse locations\n3. Generate optimized pick lists and packing slips automatically\n4. Update inventory levels in real-time across all systems\n5. Create daily fulfillment efficiency reports and metrics',
    icon: <Users className="text-pink-700 dark:text-pink-400" size={16} />,
  },
  {
    title: 'Manage product returns processing',
    query: '1. Process return requests from multiple sales channels\n2. Validate return eligibility and warranty conditions automatically\n3. Generate return authorisations and shipping labels\n4. Update inventory levels and process restocking workflows\n5. Analyse return patterns and identify quality control issues',
    icon: <RefreshCw className="text-yellow-600 dark:text-yellow-300" size={16} />,
  },
  {
    title: 'Optimise stock rotation',
    query: '1. Analyse inventory age and expiration dates across locations\n2. Identify slow-moving and obsolete stock items\n3. Calculate optimal rotation strategies and markdown recommendations\n4. Generate automated stock rotation schedules and alerts\n5. Create inventory aging reports and disposal recommendations',
    icon: <Settings className="text-orange-700 dark:text-orange-400" size={16} />,
  },
  {
    title: 'Automate receiving process',
    query: '1. Process incoming shipments and purchase orders automatically\n2. Match delivery documents with purchase orders and invoices\n3. Update inventory levels and generate receiving reports\n4. Calculate quality control metrics and defect rates\n5. Create supplier performance and receiving efficiency reports',
    icon: <BarChart3 className="text-red-700 dark:text-red-400" size={16} />,
  },
  {
    title: 'Manage warehouse capacity',
    query: '1. Analyse current warehouse space utilisation and capacity constraints\n2. Calculate storage efficiency by zone and product category\n3. Identify capacity bottlenecks and expansion opportunities\n4. Generate space optimisation recommendations and layouts\n5. Create capacity planning forecasts and growth scenarios',
    icon: <Target className="text-green-600 dark:text-green-300" size={16} />,
  },
  {
    title: 'Track inventory movements',
    query: '1. Monitor all inventory movements across warehouse locations\n2. Analyse transfer patterns and internal movement efficiency\n3. Calculate movement costs and optimise transfer routes\n4. Generate automated movement reports and exception alerts\n5. Create movement efficiency metrics and improvement recommendations',
    icon: <RefreshCw className="text-amber-700 dark:text-amber-400" size={16} />,
  },
  {
    title: 'Optimise packing operations',
    query: '1. Analyse packing data and material usage patterns\n2. Calculate optimal box sizes and packing configurations\n3. Generate automated packing instructions and material lists\n4. Track packing efficiency and error rates\n5. Create packing cost analysis and optimisation recommendations',
    icon: <Settings className="text-stone-700 dark:text-stone-400" size={16} />,
  },
  {
    title: 'Manage seasonal inventory',
    query: '1. Analyse seasonal demand patterns and inventory requirements\n2. Calculate optimal seasonal stock levels and timing\n3. Generate automated seasonal ordering and stocking schedules\n4. Monitor seasonal sell-through rates and adjust forecasts\n5. Create seasonal performance analysis and planning reports',
    icon: <Calendar className="text-fuchsia-700 dark:text-fuchsia-400" size={16} />,
  },
  {
    title: 'Automate quality control',
    query: '1. Process quality inspection data from receiving and production\n2. Analyse defect patterns and identify quality issues\n3. Generate automated quality alerts and hold procedures\n4. Track supplier quality performance and return rates\n5. Create quality control reports and improvement recommendations',
    icon: <Shield className="text-blue-600 dark:text-blue-300" size={16} />,
  },
  {
    title: 'Optimise shipping operations',
    query: '1. Analyse shipping data and carrier performance metrics\n2. Calculate optimal shipping methods and carrier selection\n3. Generate automated shipping labels and documentation\n4. Track delivery performance and customer satisfaction\n5. Create shipping cost analysis and optimisation recommendations',
    icon: <Rocket className="text-red-600 dark:text-red-300" size={16} />,
  },
  {
    title: 'Manage inventory accuracy',
    query: '1. Implement cycle counting programs across warehouse locations\n2. Analyse inventory accuracy rates and discrepancy patterns\n3. Calculate cost of inventory errors and improvement opportunities\n4. Generate automated cycle count schedules and variance reports\n5. Create inventory accuracy metrics and continuous improvement plans',
    icon: <BarChart3 className="text-slate-700 dark:text-slate-400" size={16} />,
  },
];

// Function to get random prompts
const getRandomPrompts = (count: number = 3): PromptExample[] => {
  const shuffled = [...allPrompts].sort(() => 0.5 - Math.random());
  return shuffled.slice(0, count);
};

export const Examples = ({
  onSelectPrompt,
  count = 3,
}: {
  onSelectPrompt?: (query: string) => void;
  count?: number;
}) => {
  const [displayedPrompts, setDisplayedPrompts] = useState<PromptExample[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Initialize with random prompts on mount
  useEffect(() => {
    setDisplayedPrompts(getRandomPrompts(count));
  }, [count]);

  const handleRefresh = () => {
    setIsRefreshing(true);
    setDisplayedPrompts(getRandomPrompts(count));
    setTimeout(() => setIsRefreshing(false), 300);
  };

  return (
    <div className="w-full max-w-4xl mx-auto px-4">
      <div className="group relative">
        <div className="flex gap-2 justify-center py-2 flex-wrap">
          {displayedPrompts.map((prompt, index) => (
            <motion.div
              key={`${prompt.title}-${index}`}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                duration: 0.3,
                delay: index * 0.03,
                ease: "easeOut"
              }}
            >
              <Button
                variant="outline"
                className="w-fit h-fit px-3 py-2 rounded-full border-neutral-200 dark:border-neutral-800 bg-neutral-50 hover:bg-neutral-100 dark:bg-neutral-900 dark:hover:bg-neutral-800 text-sm font-normal text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => onSelectPrompt && onSelectPrompt(prompt.query)}
              >
                <div className="flex items-center gap-2">
                  <div className="flex-shrink-0">
                    {React.cloneElement(prompt.icon as React.ReactElement, { size: 14 })}
                  </div>
                  <span className="whitespace-nowrap">{prompt.title}</span>
                </div>
              </Button>
            </motion.div>
          ))}
        </div>

        {/* Refresh button that appears on hover */}
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRefresh}
          className="absolute -top-4 right-1 h-5 w-5 p-0 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-200 hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          <motion.div
            animate={{ rotate: isRefreshing ? 360 : 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
          >
            <RefreshCw size={10} className="text-muted-foreground" />
          </motion.div>
        </Button>
      </div>
    </div>
  );
};