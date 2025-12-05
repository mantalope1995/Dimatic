"""
Property-based tests for agent model assignment.

**Feature: minimax-m2-migration, Property 2: Agent Model Assignment**
**Validates: Requirements 1.2, 1.4**

Property 2: Agent Model Assignment
For any agent creation or update operation, the system should automatically assign 
Minimax-m2 as the model, regardless of any model parameter provided in the request.
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, MagicMock, patch
from core.ai_models.registry import registry


# Check if agent_crud can be imported (requires full backend dependencies)
def _can_import_agent_crud():
    """Check if agent_crud can be imported."""
    try:
        from core.agent_crud import create_agent, update_agent
        return True
    except (ImportError, ModuleNotFoundError):
        return False


requires_agent_crud = pytest.mark.skipif(
    not _can_import_agent_crud(),
    reason="agent_crud requires full backend dependencies (sentry_sdk, etc.)"
)


# Generator for agent creation data
@st.composite
def agent_creation_data(draw):
    """Generate random agent creation data with various model specifications."""
    return {
        "name": draw(st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_characters="\x00"))),
        "model": draw(st.sampled_from([
            "gpt-4",
            "claude-3",
            "gemini-pro",
            "kortix/basic",
            "kortix/power",
            "minimax-m2",
            None,
        ])),
        "system_prompt": draw(st.text(min_size=0, max_size=500, alphabet=st.characters(blacklist_characters="\x00"))),
        "agentpress_tools": draw(st.dictionaries(
            keys=st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="\x00")),
            values=st.fixed_dictionaries({
                "enabled": st.booleans()
            }),
            max_size=5
        )),
    }


# Generator for agent update data
@st.composite
def agent_update_data(draw):
    """Generate random agent update data with various model specifications."""
    return {
        "agent_id": draw(st.uuids()).hex,
        "name": draw(st.one_of(st.none(), st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_characters="\x00")))),
        "model": draw(st.sampled_from([
            "gpt-4",
            "claude-3", 
            "gemini-pro",
            "kortix/basic",
            "kortix/power",
            "minimax-m2",
            None,
        ])),
        "system_prompt": draw(st.one_of(st.none(), st.text(min_size=0, max_size=500, alphabet=st.characters(blacklist_characters="\x00")))),
    }


@requires_agent_crud
@pytest.mark.asyncio
@given(creation_data=agent_creation_data())
@settings(max_examples=100, deadline=None)
async def test_agent_creation_assigns_minimax_m2(creation_data):
    """
    **Feature: minimax-m2-migration, Property 2: Agent Model Assignment**
    **Validates: Requirements 1.2**
    
    Property: For any agent creation operation, the system should automatically 
    assign Minimax-m2 as the model, regardless of the model parameter provided.
    """
    from core.agent_crud import create_agent
    from core.api_models.agents import AgentCreateRequest
    from core.versioning.version_service import get_version_service
    
    # Mock dependencies
    with patch('core.agent_crud.utils.db.client') as mock_db, \
         patch('core.agent_crud.verify_and_get_user_id_from_jwt') as mock_auth, \
         patch('core.agent_crud.check_agent_count_limit') as mock_limit, \
         patch('core.agent_crud._get_version_service') as mock_version_service, \
         patch('core.agent_crud.get_agent_loader') as mock_loader:
        
        # Setup mocks
        user_id = "test-user-123"
        agent_id = "test-agent-456"
        
        mock_auth.return_value = user_id
        mock_limit.return_value = {'can_create': True, 'current_count': 0, 'limit': 10, 'tier_name': 'free'}
        
        # Mock database client
        mock_client = AsyncMock()
        mock_db.return_value = mock_client
        
        # Mock agent insertion
        mock_client.table.return_value.insert.return_value.execute = AsyncMock(return_value=MagicMock(
            data=[{
                'agent_id': agent_id,
                'account_id': user_id,
                'name': creation_data['name'],
                'icon_name': 'bot',
                'icon_color': '#000000',
                'icon_background': '#F3F4F6',
                'is_default': False,
                'version_count': 1,
                'created_at': '2025-01-01T00:00:00Z',
                'updated_at': '2025-01-01T00:00:00Z',
            }]
        ))
        
        # Mock version service
        mock_version = AsyncMock()
        mock_version_service.return_value = mock_version
        
        # Capture the model passed to create_version
        captured_model = None
        
        async def capture_create_version(**kwargs):
            nonlocal captured_model
            captured_model = kwargs.get('model')
            return MagicMock(
                version_id='v1-id',
                agent_id=agent_id,
                version_number=1,
                version_name='v1',
                system_prompt=kwargs.get('system_prompt', ''),
                model=kwargs.get('model'),
                configured_mcps=kwargs.get('configured_mcps', []),
                custom_mcps=kwargs.get('custom_mcps', []),
                agentpress_tools=kwargs.get('agentpress_tools', {}),
                is_active=True,
                created_at='2025-01-01T00:00:00Z',
                updated_at='2025-01-01T00:00:00Z',
                created_by=user_id
            )
        
        mock_version.create_version = capture_create_version
        
        # Mock agent loader
        mock_loader_instance = AsyncMock()
        mock_loader.return_value = mock_loader_instance
        
        mock_agent_data = MagicMock()
        mock_agent_data.to_pydantic_model.return_value = MagicMock(
            agent_id=agent_id,
            name=creation_data['name'],
            model='minimax/minimax-m2'
        )
        mock_loader_instance.load_agent.return_value = mock_agent_data
        
        # Create agent request
        request = AgentCreateRequest(
            name=creation_data['name'],
            model=creation_data.get('model'),
            system_prompt=creation_data.get('system_prompt'),
            agentpress_tools=creation_data.get('agentpress_tools'),
        )
        
        # Execute
        result = await create_agent(request, user_id)
        
        # Verify: The model assigned should be minimax/minimax-m2
        # regardless of what was requested
        assert captured_model == 'minimax/minimax-m2', \
            f"Expected model 'minimax/minimax-m2' but got '{captured_model}' " \
            f"when creating agent with requested model '{creation_data.get('model')}'"


@requires_agent_crud
@pytest.mark.asyncio
@given(update_data=agent_update_data())
@settings(max_examples=100, deadline=None)
async def test_agent_update_assigns_minimax_m2(update_data):
    """
    **Feature: minimax-m2-migration, Property 2: Agent Model Assignment**
    **Validates: Requirements 1.4**
    
    Property: For any agent update operation, the system should automatically 
    assign Minimax-m2 as the model, regardless of the model parameter provided.
    """
    from core.agent_crud import update_agent
    from core.api_models.agents import AgentUpdateRequest
    
    # Mock dependencies
    with patch('core.agent_crud.utils.db.client') as mock_db, \
         patch('core.agent_crud.verify_and_get_user_id_from_jwt') as mock_auth, \
         patch('core.agent_crud._get_version_service') as mock_version_service, \
         patch('core.agent_crud.get_agent_loader') as mock_loader:
        
        # Setup mocks
        user_id = "test-user-123"
        agent_id = update_data['agent_id']
        
        mock_auth.return_value = user_id
        
        # Mock database client
        mock_client = AsyncMock()
        mock_db.return_value = mock_client
        
        # Mock existing agent fetch
        existing_agent = {
            'agent_id': agent_id,
            'account_id': user_id,
            'name': 'Existing Agent',
            'system_prompt': 'Old prompt',
            'model': 'gpt-4',  # Old model
            'current_version_id': 'old-version-id',
            'metadata': {},
            'created_at': '2025-01-01T00:00:00Z',
            'updated_at': '2025-01-01T00:00:00Z',
        }
        
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute = AsyncMock(
            return_value=MagicMock(data=existing_agent)
        )
        
        # Mock version service
        mock_version = AsyncMock()
        mock_version_service.return_value = mock_version
        
        # Mock get_version for existing version
        mock_version.get_version = AsyncMock(return_value=MagicMock(
            to_dict=lambda: {
                'version_id': 'old-version-id',
                'agent_id': agent_id,
                'version_number': 1,
                'version_name': 'v1',
                'system_prompt': 'Old prompt',
                'model': 'gpt-4',
                'configured_mcps': [],
                'custom_mcps': [],
                'agentpress_tools': {},
                'is_active': True,
                'created_at': '2025-01-01T00:00:00Z',
                'updated_at': '2025-01-01T00:00:00Z',
                'created_by': user_id
            }
        ))
        
        # Capture the model passed to create_version
        captured_model = None
        
        async def capture_create_version(**kwargs):
            nonlocal captured_model
            captured_model = kwargs.get('model')
            return MagicMock(
                version_id='new-version-id',
                agent_id=agent_id,
                version_number=2,
                version_name='v2',
                system_prompt=kwargs.get('system_prompt', ''),
                model=kwargs.get('model'),
                configured_mcps=kwargs.get('configured_mcps', []),
                custom_mcps=kwargs.get('custom_mcps', []),
                agentpress_tools=kwargs.get('agentpress_tools', {}),
                is_active=True,
                created_at='2025-01-01T00:00:00Z',
                updated_at='2025-01-01T00:00:00Z',
                created_by=user_id
            )
        
        mock_version.create_version = capture_create_version
        
        # Mock update result
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{**existing_agent, 'current_version_id': 'new-version-id'}])
        )
        
        # Mock agent loader
        mock_loader_instance = AsyncMock()
        mock_loader.return_value = mock_loader_instance
        
        mock_agent_data = MagicMock()
        mock_agent_data.to_pydantic_model.return_value = MagicMock(
            agent_id=agent_id,
            name=update_data.get('name') or 'Existing Agent',
            model='minimax/minimax-m2'
        )
        mock_loader_instance.load_agent.return_value = mock_agent_data
        
        # Create update request
        request = AgentUpdateRequest(
            name=update_data.get('name'),
            model=update_data.get('model'),
            system_prompt=update_data.get('system_prompt'),
        )
        
        # Execute
        result = await update_agent(agent_id, request, user_id)
        
        # Verify: If a model change was requested, it should be overridden to minimax/minimax-m2
        if update_data.get('model') is not None:
            assert captured_model == 'minimax/minimax-m2', \
                f"Expected model 'minimax/minimax-m2' but got '{captured_model}' " \
                f"when updating agent with requested model '{update_data.get('model')}'"
