from typing import Dict, List, Optional, Set
from .ai_models import Model, ModelProvider, ModelCapability, ModelPricing, ModelConfig
from core.utils.config import config
from core.utils.logger import logger

# Qwen3-VL models are the primary models for all environments
# Actual model IDs for LiteLLM - using Qwen3-VL via SiliconFlow
# Note: Using openai/ prefix because SiliconFlow API is OpenAI SDK-compatible
_BASIC_MODEL_ID = "Qwen/Qwen3-VL-235B-A22B-Instruct"
_POWER_MODEL_ID = "Qwen/Qwen3-VL-235B-A22B-Instruct"
_THINKING_MODEL_ID = "Qwen/Qwen3-VL-235B-A22B-Thinking"

# Default model IDs (these are aliases that resolve to actual IDs)
FREE_MODEL_ID = "kortix/basic"
PREMIUM_MODEL_ID = "kortix/power"
THINKING_MODEL_ID = "kortix/thinking"

class ModelRegistry:
    def __init__(self):
        self._models: Dict[str, Model] = {}
        self._aliases: Dict[str, str] = {}
        self._initialize_models()
    
    # Qwen3-VL ONLY – Primary models for all environments
    def _initialize_models(self):
        # Get SiliconFlow configuration for Qwen3-VL models
        siliconflow_api_key = config.SILICONFLOW_API_KEY if config else None
        siliconflow_api_base = config.SILICONFLOW_API_BASE if config else "https://api.siliconflow.cn/v1"
        
        # Qwen3-VL-235B-A22B-Instruct - Primary execution model
        self.register(Model(
            id="Qwen/Qwen3-VL-235B-A22B-Instruct",
            name="Qwen3-VL-235B-A22B-Instruct",
            provider=ModelProvider.SILICONFLOW,
            aliases=["qwen3-vl-instruct", "Qwen3-VL-Instruct", "qwen-vl-instruct", "kortix/basic", "kortix/power"],
            context_window=262_144,
            max_output_tokens=262_144,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
                ModelCapability.THINKING,
                ModelCapability.STRUCTURED_OUTPUT,
            ],
            pricing=ModelPricing(
                input_cost_per_million_tokens=0.40,  # Estimated pricing
                output_cost_per_million_tokens=1.20,  # Estimated pricing
            ),
            tier_availability=["free", "paid"],
            priority=100,
            recommended=True,
            enabled=True,
            config=ModelConfig(
                api_key=siliconflow_api_key,
                api_base=siliconflow_api_base,
                # Vision parameters for Qwen3-VL
                extra_body={
                    "min_pixels": 512 * 32 * 32,
                    "max_pixels": 2048 * 32 * 32,
                },
            )
        ))
        
        # Qwen3-VL-235B-A22B-Thinking - Planning model with extended reasoning
        self.register(Model(
            id="Qwen/Qwen3-VL-235B-A22B-Thinking",
            name="Qwen3-VL-235B-A22B-Thinking",
            provider=ModelProvider.SILICONFLOW,
            aliases=["qwen3-vl-thinking", "Qwen3-VL-Thinking", "qwen-vl-thinking", "kortix/thinking"],
            context_window=262_144,
            max_output_tokens=262_144,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
                ModelCapability.THINKING,
                ModelCapability.STRUCTURED_OUTPUT,
            ],
            pricing=ModelPricing(
                input_cost_per_million_tokens=0.50,  # Estimated pricing for thinking model
                output_cost_per_million_tokens=1.50,  # Estimated pricing for thinking model
            ),
            tier_availability=["paid"],  # Thinking model for paid tiers
            priority=101,
            recommended=False,  # Not recommended for general use, only for planning
            enabled=True,
            config=ModelConfig(
                api_key=siliconflow_api_key,
                api_base=siliconflow_api_base,
                # Vision parameters for Qwen3-VL
                extra_body={
                    "min_pixels": 512 * 32 * 32,
                    "max_pixels": 2048 * 32 * 32,
                },
            )
        ))
    
    def register(self, model: Model) -> None:
        self._models[model.id] = model
        for alias in model.aliases:
            self._aliases[alias] = model.id
    
    def get(self, model_id: str) -> Optional[Model]:
        if not model_id:
            return None
            
        if model_id in self._models:
            return self._models[model_id]
        
        if model_id in self._aliases:
            actual_id = self._aliases[model_id]
            return self._models.get(actual_id)
        
        return None
    
    def get_all(self, enabled_only: bool = True) -> List[Model]:
        models = list(self._models.values())
        if enabled_only:
            models = [m for m in models if m.enabled]
        return models
    
    def get_all_models(self) -> List[Model]:
        """Return all models in the registry (including disabled ones)."""
        return list(self._models.values())
    
    def get_by_tier(self, tier: str, enabled_only: bool = True) -> List[Model]:
        models = self.get_all(enabled_only)
        return [m for m in models if tier in m.tier_availability]
    
    def get_by_provider(self, provider: ModelProvider, enabled_only: bool = True) -> List[Model]:
        models = self.get_all(enabled_only)
        return [m for m in models if m.provider == provider]
    
    def get_by_capability(self, capability: ModelCapability, enabled_only: bool = True) -> List[Model]:
        models = self.get_all(enabled_only)
        return [m for m in models if capability in m.capabilities]
    
    def resolve_model_id(self, model_id: str) -> Optional[str]:
        model = self.get(model_id)
        return model.id if model else None
    
    def get_litellm_model_id(self, model_id: str) -> str:
        """Get the actual model ID to pass to LiteLLM.
        
        Resolves kortix/basic and kortix/power to actual provider model IDs.
        """
        # Map kortix model IDs to actual LiteLLM model IDs
        if model_id in ("kortix/basic", "kortix/power"):
            return _BASIC_MODEL_ID  # Both use the same underlying model
        
        if model_id == "kortix/thinking":
            return _THINKING_MODEL_ID
        
        # For other models, check if it's an alias and resolve
        model = self.get(model_id)
        if model:
            return model.id
        
        # Return as-is if not found (let LiteLLM handle it)
        return model_id
    
    def resolve_from_litellm_id(self, litellm_model_id: str) -> str:
        """Reverse lookup: resolve a LiteLLM model ID back to registry model ID.
        
        This is the inverse of get_litellm_model_id. Used by cost calculator to find pricing.
        """
        # Check if this matches our Qwen3-VL models
        if litellm_model_id == _BASIC_MODEL_ID:
            return "kortix/basic"
        
        if litellm_model_id == _THINKING_MODEL_ID:
            return "kortix/thinking"
        
        # Check if this model exists directly in registry
        if self.get(litellm_model_id):
            return litellm_model_id
        
        # Return as-is if no reverse mapping found
        return litellm_model_id
    
    def get_aliases(self, model_id: str) -> List[str]:
        model = self.get(model_id)
        return model.aliases if model else []
    
    def enable_model(self, model_id: str) -> bool:
        model = self.get(model_id)
        if model:
            model.enabled = True
            return True
        return False
    
    def disable_model(self, model_id: str) -> bool:
        model = self.get(model_id)
        if model:
            model.enabled = False
            return True
        return False
    
    def get_context_window(self, model_id: str, default: int = 31_000) -> int:
        model = self.get(model_id)
        return model.context_window if model else default
    
    def get_pricing(self, model_id: str) -> Optional[ModelPricing]:
        """Get pricing for a model, with reverse lookup for LiteLLM model IDs."""
        # First try direct lookup
        model = self.get(model_id)
        if model and model.pricing:
            return model.pricing
        
        # Try reverse lookup from LiteLLM model ID
        resolved_id = self.resolve_from_litellm_id(model_id)
        if resolved_id != model_id:
            model = self.get(resolved_id)
            if model and model.pricing:
                return model.pricing
        
        return None
    
    def to_legacy_format(self) -> Dict:
        models_dict = {}
        pricing_dict = {}
        context_windows_dict = {}
        
        for model in self.get_all(enabled_only=True):
            models_dict[model.id] = {
                "pricing": {
                    "input_cost_per_million_tokens": model.pricing.input_cost_per_million_tokens,
                    "output_cost_per_million_tokens": model.pricing.output_cost_per_million_tokens,
                } if model.pricing else None,
                "context_window": model.context_window,
                "tier_availability": model.tier_availability,
            }
            
            if model.pricing:
                pricing_dict[model.id] = {
                    "input_cost_per_million_tokens": model.pricing.input_cost_per_million_tokens,
                    "output_cost_per_million_tokens": model.pricing.output_cost_per_million_tokens,
                }
            
            context_windows_dict[model.id] = model.context_window
        
        free_models = [m.id for m in self.get_by_tier("free")]
        paid_models = [m.id for m in self.get_by_tier("paid")]
        
        # Debug logging
        from core.utils.logger import logger
        logger.debug(f"Legacy format generation: {len(free_models)} free models, {len(paid_models)} paid models")
        logger.debug(f"Free models: {free_models}")
        logger.debug(f"Paid models: {paid_models}")
        
        return {
            "MODELS": models_dict,
            "HARDCODED_MODEL_PRICES": pricing_dict,
            "MODEL_CONTEXT_WINDOWS": context_windows_dict,
            "FREE_TIER_MODELS": free_models,
            "PAID_TIER_MODELS": paid_models,
        }

registry = ModelRegistry()
