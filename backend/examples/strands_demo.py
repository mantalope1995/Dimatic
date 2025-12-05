"""
Strands Agents SDK Demo

This demonstrates how Strands could be used for agent orchestration
within the Kortix platform, potentially running inside AgentCore Runtime.

Prerequisites:
    pip install strands-agents strands-agents-tools

Environment:
    export AWS_BEDROCK_API_KEY=your_key  # For Bedrock (default)
    # OR
    export ANTHROPIC_API_KEY=your_key    # For Anthropic direct
"""

from strands import Agent, tool
from strands_tools import calculator, http_request

# Example 1: Simple agent with community tools
def demo_simple_agent():
    """Basic agent using Bedrock (default) with community tools."""
    agent = Agent(
        tools=[calculator, http_request],
        system_prompt="You are a helpful assistant that can perform calculations and fetch web data."
    )
    
    # Single query
    response = agent("What is 42 * 17?")
    print(f"Response: {response}")
    
    # Conversation continues with context
    response = agent("Now divide that result by 2")
    print(f"Follow-up: {response}")


# Example 2: Custom tool
@tool
def get_project_info(project_id: str) -> str:
    """Get information about a Kortix project.
    
    Args:
        project_id: The project ID to look up
    """
    # In real implementation, this would query Supabase
    return f"Project {project_id}: AI Research Assistant, 3 agents, 150 threads"


def demo_custom_tool():
    """Agent with custom Kortix-specific tool."""
    agent = Agent(
        tools=[get_project_info, calculator],
        system_prompt="You are a Kortix platform assistant. Help users manage their AI projects."
    )
    
    response = agent("Tell me about project proj_abc123")
    print(f"Response: {response}")


# Example 3: Using Anthropic directly (if you prefer)
def demo_anthropic_agent():
    """Agent using Anthropic API directly instead of Bedrock."""
    import os
    from strands.models.anthropic import AnthropicModel
    
    model = AnthropicModel(
        client_args={"api_key": os.environ.get("ANTHROPIC_API_KEY")},
        model_id="claude-sonnet-4-20250514",
        max_tokens=2048,
    )
    
    agent = Agent(
        model=model,
        tools=[calculator],
        system_prompt="You are a math tutor."
    )
    
    response = agent("Explain how to calculate compound interest")
    print(f"Response: {response}")


if __name__ == "__main__":
    print("=== Strands Demo ===\n")
    
    # Uncomment the demo you want to run:
    # demo_simple_agent()
    # demo_custom_tool()
    # demo_anthropic_agent()
    
    print("\nTo run a demo, uncomment one of the function calls above.")
    print("Make sure you have the required environment variables set.")
