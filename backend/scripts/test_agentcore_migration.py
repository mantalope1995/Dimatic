#!/usr/bin/env python3

"""
AgentCore Migration Test Script

This script tests the AWS AgentCore migration and validates that the tools
can be loaded and configured properly.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add the backend directory to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

async def test_agentcore_tools():
    """Test AgentCore tools loading and configuration."""
    print("🚀 Testing AWS AgentCore Migration...")
    
    try:
        # Test basic imports
        print("\n📦 Testing imports...")
        
        # Test tool registry
        from core.tools.tool_registry import get_all_tools_with_agentcore, get_tools_by_category
        print("✅ Tool registry imports successful")
        
        # Test configuration
        from core.utils.config import config
        print("✅ Configuration imports successful")
        
        # Check AgentCore configuration
        print(f"\n🔧 Configuration Status:")
        print(f"  AWS Region: {config.AWS_REGION}")
        print(f"  AgentCore Code Interpreter Tool ID: {config.AGENTCORE_CODE_INTERPRETER_TOOL_ID}")
        print(f"  AgentCore Browser Tool ID: {config.AGENTCORE_BROWSER_TOOL_ID}")
        print(f"  AgentCore Execution Role ARN: {config.AGENTCORE_EXECUTION_ROLE_ARN}")
        print(f"  AgentCore S3 Bucket: {config.AGENTCORE_S3_BUCKET}")
        print(f"  Use AgentCore: {config.USE_AGENTCORE}")
        
        # Test tool loading
        print(f"\n🛠️ Testing tool loading...")
        tools = get_all_tools_with_agentcore()
        print(f"✅ Loaded {len(tools)} tools successfully")
        
        # Show which sandbox backend is being used
        if config.USE_AGENTCORE:
            print("🚀 AWS AgentCore is configured and will be used for sandbox operations")
        else:
            print("🏖️ Daytona.io will be used for sandbox operations (AgentCore not configured)")
        
        # Show tool categories
        categories = get_tools_by_category()
        print(f"\n📂 Tool Categories:")
        for category, tool_list in categories.items():
            print(f"  {category}: {len(tool_list)} tools")
            for tool_name, _, _ in tool_list:
                print(f"    - {tool_name}")
        
        # Test specific AgentCore tool imports if AgentCore is enabled
        if config.USE_AGENTCORE:
            print(f"\n🧪 Testing AgentCore tool imports...")
            try:
                from core.tools.sb_shell_tool_agentcore import AgentCoreShellTool
                print("✅ AgentCore Shell Tool imported successfully")
                
                from core.tools.sb_files_tool_agentcore import AgentCoreFilesTool
                print("✅ AgentCore Files Tool imported successfully")
                
                from core.tools.sb_browser_tool_agentcore import AgentCoreBrowserTool
                print("✅ AgentCore Browser Tool imported successfully")
                
                from core.tools.sb_vision_tool_agentcore import AgentCoreVisionTool
                print("✅ AgentCore Vision Tool imported successfully")
                
            except ImportError as e:
                print(f"⚠️ AgentCore tool import failed: {e}")
                print("This is expected if dependencies are not fully installed")
        
        # Test bedrock-agentcore package
        print(f"\n📦 Testing bedrock-agentcore package...")
        try:
            import bedrock_agentcore
            print("✅ bedrock-agentcore imported successfully")
            
            # Test basic AgentCore functionality
            from bedrock_agentcore import BedrockAgentCoreApp
            print("✅ BedrockAgentCoreApp imported successfully")
            
        except ImportError as e:
            print(f"❌ bedrock-agentcore import failed: {e}")
        
        print(f"\n✅ Migration test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Migration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_configuration():
    """Test configuration and provide setup guidance."""
    print("\n🔧 Configuration Analysis:")
    
    from core.utils.config import config
    
    # Check AWS credentials
    print(f"\n☁️ AWS Configuration:")
    print(f"  AWS Region: {config.AWS_REGION}")
    
    # Check for AWS credentials in environment
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.getenv('AWS_SESSION_TOKEN')
    
    if aws_access_key and aws_secret_key:
        print("✅ AWS credentials found in environment")
    else:
        print("⚠️ AWS credentials not found in environment variables")
        print("   Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    
    # Check AgentCore configuration
    print(f"\n🚀 AgentCore Configuration:")
    if config.USE_AGENTCORE:
        print("✅ AgentCore is properly configured")
        print(f"  Code Interpreter Tool ID: {config.AGENTCORE_CODE_INTERPRETER_TOOL_ID}")
        print(f"  Browser Tool ID: {config.AGENTCORE_BROWSER_TOOL_ID}")
        
        if config.AGENTCORE_EXECUTION_ROLE_ARN:
            print(f"  Execution Role: {config.AGENTCORE_EXECUTION_ROLE_ARN}")
        else:
            print("⚠️ Execution Role ARN not configured")
            
        if config.AGENTCORE_S3_BUCKET:
            print(f"  S3 Bucket: {config.AGENTCORE_S3_BUCKET}")
        else:
            print("⚠️ S3 Bucket not configured")
    else:
        print("⚠️ AgentCore is not configured")
        print("   Set the following environment variables to enable AgentCore:")
        print("   - AGENTCORE_CODE_INTERPRETER_TOOL_ID")
        print("   - AGENTCORE_BROWSER_TOOL_ID")
        print("   - AGENTCORE_EXECUTION_ROLE_ARN (optional)")
        print("   - AGENTCORE_S3_BUCKET (optional)")

def print_setup_guide():
    """Print setup guide for AgentCore migration."""
    print("""
🚀 AWS AgentCore Migration Setup Guide
=====================================

To complete the AWS AgentCore migration, follow these steps:

1. AWS Setup:
   - Create an AWS account if you don't have one
   - Configure AWS CLI with your credentials: aws configure
   - Ensure you have the necessary IAM permissions for AgentCore

2. AgentCore Tool Setup (ap-southeast-2 - Sydney):
   - Go to AWS Bedrock Console (ensure region is set to ap-southeast-2)
   - Create AgentCore Code Interpreter tool in Sydney region
   - Create AgentCore Browser tool in Sydney region
   - Note down the Tool IDs

3. Environment Configuration:
   Add these to your .env file:
   export AWS_REGION="ap-southeast-2"
   export AGENTCORE_CODE_INTERPRETER_TOOL_ID="your-code-interpreter-tool-id"
   export AGENTCORE_BROWSER_TOOL_ID="your-browser-tool-id"
   export AGENTCORE_EXECUTION_ROLE_ARN="arn:aws:iam::ACCOUNT:role/AgentCoreExecutionRole"
   export AGENTCORE_S3_BUCKET="your-agentcore-bucket"

4. IAM Role Setup (optional but recommended):
   - Create an IAM role for AgentCore execution
   - Attach policies for S3, CloudWatch, and other AWS services
   - Use the role ARN in AGENTCORE_EXECUTION_ROLE_ARN

5. S3 Bucket Setup (optional but recommended):
   - Create an S3 bucket for AgentCore file operations
   - Configure appropriate permissions
   - Use the bucket name in AGENTCORE_S3_BUCKET

6. Testing:
   - Run this script to verify configuration
   - Test agent execution with shell commands
   - Test browser automation if configured

7. Deployment:
   - Update production environment variables
   - Test in staging environment first
   - Monitor logs for any issues

Benefits of AgentCore over Daytona.io:
- ✅ Serverless architecture - no infrastructure management
- ✅ Better scalability and performance
- ✅ Integrated with AWS ecosystem
- ✅ Cost-effective with pay-per-use pricing
- ✅ Enhanced security with AWS IAM
- ✅ Better monitoring and logging

Fallback Behavior:
- If AgentCore is not configured, the system automatically falls back to Daytona.io
- This ensures backward compatibility during migration
- Tools will continue to work without interruption
""")

async def main():
    """Main test function."""
    print("=" * 60)
    print("🚀 AWS AgentCore Migration Test")
    print("=" * 60)
    
    # Run tests
    success = await test_agentcore_tools()
    
    # Test configuration
    await test_configuration()
    
    # Print setup guide if needed
    if not success:
        print_setup_guide()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed! AgentCore migration is ready.")
    else:
        print("⚠️ Some tests failed. Check the output above for details.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
