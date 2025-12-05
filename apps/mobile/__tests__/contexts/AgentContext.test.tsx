/**
 * Unit tests for AgentContext
 * 
 * Tests that model-related state has been removed from AgentContext
 * as part of the Minimax-m2 migration (Requirement 11.5)
 */

import React from 'react';
import { renderHook } from '@testing-library/react-hooks';
import { AgentProvider, useAgent } from '@/contexts/AgentContext';

// Mock dependencies
jest.mock('@/lib/agents', () => ({
  useAgents: () => ({
    data: {
      agents: [
        {
          agent_id: 'agent-1',
          name: 'Test Agent',
          description: 'Test Description',
        },
      ],
    },
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  }),
}));

jest.mock('@/contexts/AuthContext', () => ({
  useAuthContext: () => ({
    session: {
      user: { id: 'user-1' },
    },
  }),
}));

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
}));

describe('AgentContext - Model State Removal', () => {
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <AgentProvider>{children}</AgentProvider>
  );

  it('should not expose selectedModelId in context', () => {
    const { result } = renderHook(() => useAgent(), { wrapper });
    
    // selectedModelId should not be in the context
    expect(result.current).not.toHaveProperty('selectedModelId');
  });

  it('should not expose selectModel function in context', () => {
    const { result } = renderHook(() => useAgent(), { wrapper });
    
    // selectModel function should not be in the context
    expect(result.current).not.toHaveProperty('selectModel');
  });

  it('should still expose agent-related state and functions', () => {
    const { result } = renderHook(() => useAgent(), { wrapper });
    
    // Agent-related properties should still be present
    expect(result.current).toHaveProperty('selectedAgentId');
    expect(result.current).toHaveProperty('agents');
    expect(result.current).toHaveProperty('selectAgent');
    expect(result.current).toHaveProperty('loadAgents');
  });

  it('should have correct context type without model properties', () => {
    const { result } = renderHook(() => useAgent(), { wrapper });
    
    const contextKeys = Object.keys(result.current);
    
    // Should not include model-related keys
    expect(contextKeys).not.toContain('selectedModelId');
    expect(contextKeys).not.toContain('selectModel');
    
    // Should include agent-related keys
    expect(contextKeys).toContain('selectedAgentId');
    expect(contextKeys).toContain('selectAgent');
    expect(contextKeys).toContain('agents');
  });
});
