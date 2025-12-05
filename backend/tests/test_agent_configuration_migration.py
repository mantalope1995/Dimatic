"""
Property-based tests for agent configuration migration.

**Feature: minimax-m2-migration, Property 20: Agent Configuration Migration**
**Validates: Requirements 9.5**

Property 20: Agent Configuration Migration
For any agent configuration being migrated, the system should update the model 
to Minimax-m2 while preserving all other configuration settings.
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, MagicMock, patch


# Check if agent modules can be imported (requires full backend dependencies)
def _can_import_agent_modules():
    """Check if agent modules can be imported."""
    try:
        from core.agent_loader import AgentLoader
        from core.agent_crud import update_agent
        return True
    except (ImportError, ModuleNotFoundError):
        return False


requires_agent_modules = pytest.mark.skipif(
    not _can_import_agent_modules(),
    reason="Agent modules require full backend dependencies (sentry_sdk, etc.)"
)


# Generator for agent configurations
@st.composite
def agent_configuration(draw):
    """Generate random agent configurations with various settings."""
    return {
        "agent_id": draw(st.uuids()).hex,
        "name": draw(st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_characters="\x00"))),
        "description": draw(st.one_of(st.none(), st.text(min_size=0, max_size=500, alphabet=st.characters(blacklist_characters="\x00")))),
        "system_prompt": draw(st.text(min_size=1, max_size=1000, alphabet=st.characters(blacklist_characters="\x00"))),
        "model": draw(st.sampled_from([
            "gpt-4",
            "claude-3",
            "gemini-pro",
            "kortix/basic",
            "kortix/power",
        ])),
        "configured_mcps": draw(st.lists(
            st.fixed_dictionaries({
                "name": st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\x00")),
                "enabled": st.booleans()
            }),
            max_size=5
        )),
        "custom_mcps": draw(st.lists(
            st.fixed_dictionaries({
                "name": st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\x00")),
                "command": st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_characters="\x00"))
            }),
            max_size=3
        )),
        "agentpress_tools": draw(st.dictionaries(
            keys=st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="\x00")),
            values=st.fixed_dictionaries({
                "enabled": st.booleans(),
                "config": st.dictionaries(
                    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="\x00")),
                    values=st.one_of(st.booleans(), st.text(max_size=50, alphabet=st.characters(blacklist_characters="\x00")), st.integers()),
                    max_size=3
                )
            }),
            max_size=5
        )),
        "is_default": draw(st.booleans()),
        "tags": draw(st.lists(st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="\x00")), max_size=5)),
    }


@requires_agent_modules
@pytest.mark.asyncio
@given(config=agent_configuration())
@settings(max_examples=100, deadline=None)
async def test_agent_loading_overrides_model_to_minimax_m2(config):
    """
    **Feature: minimax-m2-migration, Property 20: Agent Configuration Migration**
    **Validates: Requirements 9.5**
    
    Property: For any agent configuration being loaded, the system should override 
    the model to Minimax-m2 while preserving all other configuration settings.
    """
    from core.agent_loader import AgentLoader
    
    # Mock dependencies
    with patch('core.agent_loader.DBConnection') as mock_db_conn:
        
        # Setup mocks
        user_id = "test-user-123"
        agent_id = config['agent_id']
        
        mock_db = AsyncMock()
        mock_db_conn.return_value = mock_db
        
        mock_client = AsyncMock()
        mock_db.client = mock_client
        
        # Mock agent row from database
        agent_row = {
            'agent_id': agent_id,
            'account_id': user_id,
            'name': config['name'],
            'description': config['description'],
            'is_default': config['is_default'],
            'is_public': False,
            'tags': config['tags'],
            'icon_name': 'bot',
            'icon_color': '#000000',
            'icon_background': '#F3F4F6',
            'created_at': '2025-01-01T00:00:00Z',
            'updated_at': '2025-01-01T00:00:00Z',
            'current_version_id': 'version-123',
            'version_count': 1,
            'metadata': {},
        }
        
        # Mock database query for agent
        mock_client.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[agent_row])
        )
        
        # Mock version service
        with patch('core.agent_loader.get_version_service') as mock_version_service:
            mock_version = AsyncMock()
            mock_version_service.return_value = mock_version
            
            # Mock version data with old model
            version_data = {
                'version_id': 'version-123',
                'agent_id': agent_id,
                'version_number': 1,
                'version_name': 'v1',
                'system_prompt': config['system_prompt'],
                'model': config['model'],  # Old model
                'config': {
                    'system_prompt': config['system_prompt'],
                    'model': config['model'],  # Old model
                    'tools': {
                        'mcp': config['configured_mcps'],
                        'custom_mcp': config['custom_mcps'],
                        'agentpress': config['agentpress_tools']
                    },
                    'triggers': []
                },
                'created_at': '2025-01-01T00:00:00Z',
                'updated_at': '2025-01-01T00:00:00Z',
                'created_by': user_id
            }
            
            mock_version.get_version = AsyncMock(return_value=MagicMock(
                to_dict=lambda: version_data
            ))
            
            # Mock cache functions
            with patch('core.agent_loader.get_cached_agent_config', return_value=None), \
                 patch('core.agent_loader.set_cached_agent_config'):
                
                # Create loader and load agent
                loader = AgentLoader(mock_db)
                agent_data = await loader.load_agent(agent_id, user_id, load_config=True)
                
                # Verify: Model should be overridden to minimax/minimax-m2
                assert agent_data.model == 'minimax/minimax-m2', \
                    f"Expected model 'minimax/minimax-m2' but got '{agent_data.model}' " \
                    f"when loading agent with original model '{config['model']}'"
                
                # Verify: All other settings should be preserved
                assert agent_data.name == config['name'], \
                    f"Agent name changed during migration: expected '{config['name']}', got '{agent_data.name}'"
                
                assert agent_data.description == config['description'], \
                    f"Agent description changed during migration"
                
                assert agent_data.system_prompt == config['system_prompt'], \
                    f"System prompt changed during migration"
                
                assert agent_data.configured_mcps == config['configured_mcps'], \
                    f"Configured MCPs changed during migration"
                
                assert agent_data.custom_mcps == config['custom_mcps'], \
                    f"Custom MCPs changed during migration"
                
                # Compare agentpress tools (may be transformed, so check keys)
                if config['agentpress_tools']:
                    assert set(agent_data.agentpress_tools.keys()) == set(config['agentpress_tools'].keys()), \
                        f"AgentPress tools changed during migration"
                
                assert agent_data.is_default == config['is_default'], \
                    f"is_default flag changed during migration"
                
                assert agent_data.tags == config['tags'], \
                    f"Tags changed during migration"


@requires_agent_modules
@pytest.mark.asyncio
@given(config=agent_configuration())
@settings(max_examples=100, deadline=None)
async def test_agent_update_preserves_non_model_settings(config):
    """
    **Feature: minimax-m2-migration, Property 20: Agent Configuration Migration**
    **Validates: Requirements 9.5**
    
    Property: When updating an agent's model to Minimax-m2, all other configuration 
    settings should remain unchanged.
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
        agent_id = config['agent_id']
        
        mock_auth.return_value = user_id
        
        # Mock database client
        mock_client = AsyncMock()
        mock_db.return_value = mock_client
        
        # Mock existing agent with old configuration
        existing_agent = {
            'agent_id': agent_id,
            'account_id': user_id,
            'name': config['name'],
            'description': config['description'],
            'system_prompt': config['system_prompt'],
            'model': config['model'],  # Old model
            'current_version_id': 'old-version-id',
            'metadata': {},
            'is_default': config['is_default'],
            'tags': config['tags'],
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
                'system_prompt': config['system_prompt'],
                'model': config['model'],  # Old model
                'configured_mcps': config['configured_mcps'],
                'custom_mcps': config['custom_mcps'],
                'agentpress_tools': config['agentpress_tools'],
                'is_active': True,
                'created_at': '2025-01-01T00:00:00Z',
                'updated_at': '2025-01-01T00:00:00Z',
                'created_by': user_id
            }
        ))
        
        # Capture the parameters passed to create_version
        captured_params = {}
        
        async def capture_create_version(**kwargs):
            nonlocal captured_params
            captured_params = kwargs.copy()
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
            name=config['name'],
            model='minimax/minimax-m2',
            system_prompt=config['system_prompt'],
            configured_mcps=config['configured_mcps'],
            custom_mcps=config['custom_mcps'],
            agentpress_tools=config['agentpress_tools'],
        )
        mock_loader_instance.load_agent.return_value = mock_agent_data
        
        # Create update request that only changes the model
        request = AgentUpdateRequest(
            model='minimax/minimax-m2'
        )
        
        # Execute
        result = await update_agent(agent_id, request, user_id)
        
        # Verify: Model should be updated to minimax/minimax-m2
        assert captured_params.get('model') == 'minimax/minimax-m2', \
            f"Expected model 'minimax/minimax-m2' but got '{captured_params.get('model')}'"
        
        # Verify: All other settings should be preserved
        assert captured_params.get('system_prompt') == config['system_prompt'], \
            f"System prompt changed during model update"
        
        assert captured_params.get('configured_mcps') == config['configured_mcps'], \
            f"Configured MCPs changed during model update"
        
        assert captured_params.get('custom_mcps') == config['custom_mcps'], \
            f"Custom MCPs changed during model update"
        
        # AgentPress tools should be preserved (with core tools ensured)
        assert set(captured_params.get('agentpress_tools', {}).keys()).issuperset(set(config['agentpress_tools'].keys())), \
            f"AgentPress tools lost during model update"
