'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import {
  AlertTriangle,
  BarChart3,
  Bot,
  Briefcase,
  Calendar,
  Camera,
  DollarSign,
  FileText,
  Globe,
  Heart,
  PenTool,
  RefreshCw,
  Rocket,
  Settings,
  Shield,
  Target,
  TrendingUp,
  Users,
  Brain,
} from 'lucide-react';

type PromptExample = {
  title: string;
  query: string;
  icon: React.ReactNode;
};

const allPrompts: PromptExample[] = [
  {
    title: 'Identify dead stock items',
    query: '1. Analyse inventory spreadsheet for slow-moving products\n2. Calculate days on hand and turnover rates\n3. Flag items over 90 days with no sales\n4. Estimate cash tied up in dead stock\n5. Generate report with discount/liquidation recommendations',
    icon: <BarChart3 className="text-red-700 dark:text-red-400" size={16} />,
  },
  {
    title: 'Predict upcoming stockouts',
    query: '1. Analyse sales velocity for all active SKUs\n2. Calculate current stock levels vs daily sell-through\n3. Forecast stockout dates for bestsellers\n4. Factor in supplier lead times\n5. Generate reorder alerts with recommended quantities',
    icon: <AlertTriangle className="text-orange-700 dark:text-orange-400" size={16} />,
  },
  {
    title: 'Reconcile multi-channel sales',
    query: '1. Pull sales data from Shopify, eBay, and physical POS\n2. Cross-reference inventory levels across channels\n3. Identify discrepancies and overselling risks\n4. Update master inventory spreadsheet\n5. Generate daily reconciliation report with accuracy score',
    icon: <FileText className="text-blue-700 dark:text-blue-400" size={16} />,
  },
  {
    title: 'Calculate true SKU profitability',
    query: '1. Analyse sales data with product costs and margins\n2. Factor in carrying costs and turnover rates\n3. Calculate profit per SKU after all expenses\n4. Identify high-volume low-profit items\n5. Create profitability dashboard with recommendations',
    icon: <DollarSign className="text-green-700 dark:text-green-400" size={16} />,
  },
  {
    title: 'Monitor competitor pricing',
    query: '1. Search competitor websites for matching SKUs\n2. Track pricing changes over past 30 days\n3. Compare your prices vs market average\n4. Identify overpriced and underpriced items\n5. Generate pricing adjustment recommendations',
    icon: <Globe className="text-purple-700 dark:text-purple-400" size={16} />,
  },
  {
    title: 'Analyse seasonal demand patterns',
    query: '1. Review 12 months of sales history by SKU\n2. Identify seasonal peaks and troughs\n3. Calculate seasonal demand multipliers\n4. Forecast next quarter inventory needs\n5. Create seasonal purchasing plan with timing',
    icon: <TrendingUp className="text-indigo-700 dark:text-indigo-400" size={16} />,
  },
  {
    title: 'Audit supplier performance',
    query: '1. Analyse purchase orders and delivery records\n2. Calculate on-time delivery rates by supplier\n3. Track order accuracy and quality issues\n4. Compare pricing trends over time\n5. Generate supplier scorecard with recommendations',
    icon: <Briefcase className="text-teal-700 dark:text-teal-400" size={16} />,
  },
  {
    title: 'Optimise reorder quantities',
    query: '1. Analyse sales data and supplier lead times\n2. Calculate economic order quantities by SKU\n3. Factor in storage costs and cash flow constraints\n4. Optimise order frequency vs holding costs\n5. Create purchasing plan with optimal order sizes',
    icon: <Target className="text-cyan-700 dark:text-cyan-400" size={16} />,
  },
  {
    title: 'Generate stock take schedule',
    query: '1. Analyse inventory by category and value\n2. Prioritise high-value and fast-moving items\n3. Create cycle count schedule by ABC classification\n4. Assign count frequency and responsibilities\n5. Build automated stock take calendar and checklist',
    icon: <Calendar className="text-rose-700 dark:text-rose-400" size={16} />,
  },
  {
    title: 'Track inventory accuracy',
    query: '1. Compare physical counts vs system records\n2. Calculate accuracy percentage by category\n3. Identify patterns in discrepancies\n4. Track improvement over time\n5. Generate monthly accuracy report with root causes',
    icon: <Shield className="text-yellow-600 dark:text-yellow-300" size={16} />,
  },
  {
    title: 'Analyse product bundle opportunities',
    query: '1. Review sales data for purchase patterns\n2. Identify frequently bought together items\n3. Calculate margin impact of bundling\n4. Test bundle pricing scenarios\n5. Create bundle recommendations with profit projections',
    icon: <Brain className="text-fuchsia-700 dark:text-fuchsia-400" size={16} />,
  },
  {
    title: 'Forecast cash flow from inventory',
    query: '1. Analyse current inventory value by age\n2. Project sales velocity and turnover\n3. Calculate expected cash conversion timeline\n4. Identify cash flow risks from slow movers\n5. Generate cash flow forecast with optimisation plan',
    icon: <Rocket className="text-green-600 dark:text-green-300" size={16} />,
  },
  {
    title: 'Process supplier invoices',
    query: '1. Scan supplier invoices from email and folders\n2. Extract invoice numbers, dates, amounts, SKUs\n3. Match against purchase orders\n4. Flag discrepancies and overcharges\n5. Build invoice tracking spreadsheet with payment schedule',
    icon: <Heart className="text-amber-700 dark:text-amber-400" size={16} />,
  },
  {
    title: 'Research new suppliers',
    query: '1. Search for alternative suppliers for top 20 SKUs\n2. Compare pricing, MOQs, and lead times\n3. Check reviews and business credentials\n4. Analyse total landed cost including freight\n5. Create supplier comparison report with recommendations',
    icon: <Users className="text-blue-600 dark:text-blue-300" size={16} />,
  },
  {
    title: 'Set up low-stock alerts',
    query: '1. Analyse sales velocity for all active SKUs\n2. Calculate reorder points based on lead time\n3. Set up automatic low-stock monitoring\n4. Configure email alerts with recommended orders\n5. Create weekly stock status dashboard',
    icon: <Settings className="text-red-700 dark:text-red-400" size={16} />,
  },
  {
    title: 'Benchmark inventory metrics',
    query: '1. Calculate inventory turnover and days on hand\n2. Research industry benchmarks for your sector\n3. Compare your metrics vs industry average\n4. Identify improvement opportunities\n5. Create performance dashboard with targets',
    icon: <BarChart3 className="text-slate-700 dark:text-slate-400" size={16} />,
  },
  {
    title: 'Analyse ABC inventory classification',
    query: '1. Categorise all SKUs by revenue contribution\n2. Calculate cumulative revenue percentages\n3. Assign A, B, C classifications\n4. Determine appropriate stock policies per category\n5. Create management strategy for each tier',
    icon: <PenTool className="text-indigo-700 dark:text-indigo-400" size={16} />,
  },
  {
    title: 'Compare warehouse locations',
    query: '1. Research warehouse options in Sydney, Melbourne, Brisbane\n2. Compare rental costs, proximity to customers, labour costs\n3. Analyse logistics costs and delivery times\n4. Calculate total cost of ownership per location\n5. Create comparison spreadsheet with recommendations',
    icon: <Camera className="text-stone-700 dark:text-stone-400" size={16} />,
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