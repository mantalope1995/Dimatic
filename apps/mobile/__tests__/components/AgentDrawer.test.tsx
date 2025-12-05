/**
 * Unit tests for AgentDrawer component
 * 
 * Tests that model selection UI has been removed from the mobile app
 * as part of the Minimax-m2 migration (Requirement 11.5)
 */

import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { AgentDrawer } from '@/components/agents/AgentDrawer';

// Mock dependencies
jest.mock('@/contexts', () => ({
  useLanguage: () => ({ t: (key: string) => key }),
}));

jest.mock('@/contexts/AgentContext', () => ({
  useAgent: () => ({
    agents: [
      {
        agent_id: 'agent-1',
        name: 'Test Agent',
        description: 'Test Description',
      },
    ],
    selectedAgentId: 'agent-1',
    selectAgent: jest.fn(),
    isLoading: false,
    loadAgents: jest.fn(),
  }),
}));

jest.mock('@/hooks', () => ({
  useAdvancedFeatures: () => ({ isEnabled: false }),
}));

jest.mock('@/contexts/BillingContext', () => ({
  useBillingContext: () => ({
    hasActiveSubscription: false,
    subscriptionData: null,
  }),
}));

jest.mock('nativewind', () => ({
  useColorScheme: () => ({ colorScheme: 'light' }),
}));

jest.mock('@gorhom/bottom-sheet', () => ({
  __esModule: true,
  default: React.forwardRef((props: any, ref: any) => null),
  BottomSheetBackdrop: () => null,
  BottomSheetScrollView: ({ children }: any) => children,
}));

describe('AgentDrawer - Model UI Removal', () => {
  const defaultProps = {
    visible: true,
    onClose: jest.fn(),
  };

  it('should not render model selection UI', () => {
    const { queryByText } = render(<AgentDrawer {...defaultProps} />);
    
    // Model selection text should not be present
    expect(queryByText('models.selectModel')).toBeNull();
    expect(queryByText('Select Model')).toBeNull();
    expect(queryByText('Choose an AI model')).toBeNull();
  });

  it('should not display model information', () => {
    const { queryByText } = render(<AgentDrawer {...defaultProps} />);
    
    // Model-related labels should not be present
    expect(queryByText('Available Models')).toBeNull();
    expect(queryByText('Premium Models')).toBeNull();
    expect(queryByText('Power')).toBeNull();
    expect(queryByText('Basic')).toBeNull();
  });

  it('should not render ModelAvatar component', () => {
    const { queryByTestId } = render(<AgentDrawer {...defaultProps} />);
    
    // ModelAvatar should not be rendered
    expect(queryByTestId('model-avatar')).toBeNull();
  });

  it('should still render agent selection UI', () => {
    const { getByText } = render(<AgentDrawer {...defaultProps} />);
    
    // Agent selection should still be present
    expect(getByText('agents.myWorkers')).toBeTruthy();
  });

  it('should not have models view in navigation', () => {
    const { queryByText } = render(<AgentDrawer {...defaultProps} />);
    
    // Should not be able to navigate to models view
    expect(queryByText('Search models...')).toBeNull();
  });
});
